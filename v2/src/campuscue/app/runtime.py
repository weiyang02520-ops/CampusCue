"""CampusRuntime - M1 composition root.

State machine: CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED | FAILED.
M1 wires only: Config, EchoHandler, Router, EventBus, OneBotAdapter.
No DB / Provider / Reminder / Agent / API (M2+).

Outbound (M1.1 finding B): routing + send happen INSIDE the EventBus handler
so max_in_flight bounds the complete event->route->outbound pipeline, and
send failures are caught here (never "Task exception was never retrieved").
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from campuscue.adapters.onebot.adapter import ActionFailure, OneBotAdapter
from campuscue.config import RuntimeConfig
from campuscue.core.bus import EventBus
from campuscue.core.router import Router
from campuscue.handlers.echo import echo_handler

logger = logging.getLogger("campuscue.runtime")
API_STARTUP_TIMEOUT_S = 5.0


class RuntimeState(str, Enum):
    CREATED = "CREATED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class CampusRuntime:
    def __init__(self, config: RuntimeConfig) -> None:
        self.config = config
        self.state = RuntimeState.CREATED
        self.bus: EventBus | None = None
        self.router: Router | None = None
        self.adapter: OneBotAdapter | None = None
        self._database = None  # owned DB (M2 opt-in); disposed on shutdown
        self._task_repo = None
        self._reminder_repo = None
        self._source_repo = None
        self._extraction_repo = None
        self._provider_repo = None
        self._realtime = None
        self._api_server = None
        self._api_task = None
        self._api_log_handler = None
        self._started_at = None
        self._api_deps = None
        self._api_app = None
        self._api_startup_exception: BaseException | None = None

    @property
    def uptime_seconds(self) -> float:
        import time as _time
        if self._started_at is None:
            return 0.0
        return _time.monotonic() - self._started_at


    async def start(self) -> None:
        self.state = RuntimeState.STARTING
        try:
            # wiring order matters: handlers/router ready before events flow (no startup race)
            self.router = Router()
            if self.config.tasks.enabled:
                await self._init_task_pipeline()
            # TaskPipeline handler first (returns None for hello), EchoHandler last
            self.router.add_handler(echo_handler)
            self.bus = EventBus(
                queue_maxsize=self.config.event_bus.queue_maxsize,
                max_in_flight=self.config.event_bus.max_in_flight,
            )
            self.bus.subscribe(self._route_event)
            self.bus.start()

            self.adapter = OneBotAdapter(
                self.config.onebot,
                on_event=self.bus.publish,
                on_connection=self._on_adapter_connection,
            )
            await self.adapter.start()
            if self.config.api.enabled:
                await self._init_api()
            import time as _time
            self._started_at = _time.monotonic()
            self.state = RuntimeState.RUNNING
            logger.info("campus runtime RUNNING")
        except Exception as e:
            logger.exception("runtime startup failed: %s", e)
            await self._cleanup_after_failure()
            self.state = RuntimeState.FAILED
            raise

    async def _init_task_pipeline(self) -> None:
        """M2/M3/M4 opt-in wiring: DB + repositories + services + pipeline
        handler (+ M3 reminder scheduler + M4 Agent). Pipeline handler added
        AFTER the Agent handler, BEFORE EchoHandler."""
        from zoneinfo import ZoneInfo

        import os as _os

        from campuscue.providers.manager import ProviderManager
        from campuscue.repositories.repositories import (
            ExtractionRepository,
            ProviderConfigRepository,
            ReminderRepository,
            SourceRepository,
            TaskRepository,
        )
        from campuscue.services.reminder_scheduler import ReminderScheduler
        from campuscue.services.reminder_service import NoopDelivery, ReminderService
        from campuscue.services.task_service import TaskService
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.tasks.pipeline import TaskPipeline

        assert self.router is not None
        database = Database(
            DatabaseConfig(
                path=self.config.tasks.database_path,
                env=_os.environ.get("CAMPUSCUE_ENV", "production"),
            )
        )
        await database.initialize()  # includes v1->v2 migration when needed (M3)
        self._database = database
        sf = database.session
        tz = ZoneInfo(self.config.tasks.timezone)
        task_repo = TaskRepository(sf)
        reminder_repo = ReminderRepository(sf)
        source_repo = SourceRepository(sf)
        extraction_repo = ExtractionRepository(sf)
        provider_repo = ProviderConfigRepository(sf)
        self._task_repo = task_repo
        self._reminder_repo = reminder_repo
        self._source_repo = source_repo
        self._extraction_repo = extraction_repo
        self._provider_repo = provider_repo

        # M5 RealtimeHub is created up-front when API is enabled; it is injected
        # into services so mutations from ANY path publish SSE notifications.
        realtime_hub = None
        if self.config.api.enabled:
            from campuscue.api.realtime import RealtimeHub
            realtime_hub = RealtimeHub(queue_size=self.config.api.sse_queue_size)
            self._realtime = realtime_hub

        # M3 reminder subsystem (optional/injected; M2 works without it)
        reminder_service: ReminderService | None = None
        reminder_scheduler: ReminderScheduler | None = None
        if self.config.reminders.enabled:
            from campuscue.tasks.reminder_policy import ReminderPolicy

            reminder_scheduler = ReminderScheduler(fire_callback=self._fire_reminder)
            # M3.1-A: canonical ReminderPolicy built from RuntimeConfig.reminders
            # (timezone/min_lead_seconds/quiet hours are runtime-consumed, not
            # just declared). No duplicate policy configuration elsewhere.
            reminder_service = ReminderService(
                reminder_repo,
                task_repo,
                scheduler=reminder_scheduler,
                timezone=ZoneInfo(self.config.reminders.timezone),
                policy=ReminderPolicy(
                    min_lead_seconds=self.config.reminders.min_lead_seconds,
                    quiet_start_hour=self.config.reminders.quiet_start_hour,
                    quiet_end_hour=self.config.reminders.quiet_end_hour,
                ),
                notifier=realtime_hub,
            )
            reminder_service.set_delivery(NoopDelivery())
            self._reminder_service = reminder_service
            self._reminder_scheduler = reminder_scheduler

        # ONE shared TaskService — the business gate (M4 §39): Agent tools use
        # the SAME correctly-wired TaskService as the application business layer.
        task_service = TaskService(
            task_repo,
            reminder_service=reminder_service,
            notifier=realtime_hub,
        )
        self._task_service = task_service
        self._provider_manager = ProviderManager(provider_repo)
        pipeline = TaskPipeline(
            sources=source_repo,
            extractions=extraction_repo,
            task_service=task_service,
            provider_manager=self._provider_manager,
            timezone=tz,
            confidence_threshold=self.config.tasks.confidence_threshold,
            notifier=realtime_hub,
        )
        self._pipeline = pipeline

        # M4 Agent: registered BEFORE the pipeline handler so an explicitly
        # Agent-directed message never ALSO runs automatic Task Extraction
        # (M4 §36/§37: one query -> one LLM call chain).
        if self.config.agent.enabled:
            await self._init_agent(tz=tz, sf=sf, task_service=task_service, reminder_service=reminder_service)
        self.router.add_handler(pipeline.handle)

        # M3 scheduler lifecycle: DB ready -> resync from facts -> start
        if reminder_scheduler is not None and reminder_service is not None:
            await reminder_service.resync_all()
            reminder_scheduler.start()

    async def _init_agent(
        self,
        *,
        tz,
        sf,
        task_service,
        reminder_service,
    ) -> None:
        """M4 composition: ToolRegistry + Task Tools + CampusAgentRuntime +
        AgentChatHandler. Provider may be None (graceful "未配置模型服务")."""
        from campuscue.agents.runtime import CampusAgentRuntime
        from campuscue.handlers.agent import AgentChatHandler
        from campuscue.providers.errors import NoProviderConfiguredError
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.storage.clock import SystemClock
        from campuscue.tools.registry import ToolRegistry
        from campuscue.tools.task_tools import register_task_tools

        assert self.router is not None
        try:
            provider = await self._provider_manager.get_default()
        except NoProviderConfiguredError:
            provider = None
        registry = ToolRegistry(default_timeout_s=self.config.agent.tool_timeout_s)
        register_task_tools(
            registry,
            task_service=task_service,
            reminder_service=reminder_service,
            tz=tz,
            clock=SystemClock(),
        )
        agent_runtime = CampusAgentRuntime(
            tools=registry,
            provider=provider,
            timezone=tz,
            max_context_tokens=provider.max_context_tokens if provider is not None else None,
            reserve_output_tokens=self.config.agent.reserve_output_tokens,
            max_steps=self.config.agent.max_steps,
            tool_timeout_s=self.config.agent.tool_timeout_s,
            conversation_max_messages=self.config.agent.conversation_max_messages,
            conversation_max_threads=self.config.agent.conversation_max_threads,
        )
        handler = AgentChatHandler(
            runtime=agent_runtime,
            sources=SourceRepository(sf),
            timezone=tz,
        )
        self.router.add_handler(handler.handle)  # BEFORE pipeline (M4 §37)
        self._agent_runtime = agent_runtime
        self._agent_handler = handler

    async def _init_api(self) -> None:
        """M5: start FastAPI as the LAST runtime component. Owned task is kept
        and cancelled on shutdown; startup failure rolls back via start()."""
        import logging

        import uvicorn

        from campuscue.api.app import create_app
        from campuscue.api.dependencies import APIDependencies
        from campuscue.api.logbuffer import LogBufferHandler
        from campuscue.repositories.repositories import SettingRepository
        from campuscue.services.provider_service import ProviderService
        from campuscue.services.settings_service import SettingsService
        from campuscue.services.source_service import SourceService
        from campuscue.services.system_service import SystemService

        assert self._database is not None and self._task_service is not None
        deps = APIDependencies(
            config=self.config.api,
            runtime=self,
            database=self._database,
            source_service=SourceService(self._source_repo),
            task_service=self._task_service,
            reminder_service=getattr(self, "_reminder_service", None),
            provider_service=ProviderService(self._provider_repo, self._provider_manager),
            settings_service=SettingsService(
                SettingRepository(self._database.session),
                default_timezone=self.config.tasks.timezone,
            ),
            system_service=SystemService(
                self._database.session,
                self._task_service,
                reminder_service=getattr(self, "_reminder_service", None),
                provider_manager=self._provider_manager,
            ),
            agent_runtime=getattr(self, "_agent_runtime", None),
            agent_handler=getattr(self, "_agent_handler", None),
            realtime=getattr(self, "_realtime", None),
        )
        self._api_deps = deps
        app = create_app(deps)
        self._api_app = app
        # attach redacted in-memory diagnostic log capture
        handler = LogBufferHandler(deps.log_buffer)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("campuscue").addHandler(handler)
        self._api_log_handler = handler

        config = uvicorn.Config(
            app,
            host=self.config.api.host,
            port=self.config.api.port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        self._api_server = server
        self._api_startup_exception = None
        self._api_task = asyncio.create_task(self._serve_api(server), name="campuscue.api")
        try:
            await asyncio.wait_for(
                self._wait_for_api_ready(server, self._api_task),
                timeout=API_STARTUP_TIMEOUT_S,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError("API server startup timed out") from exc
        logger.info("campuscue api listening on http://%s:%s", self.config.api.host, self.config.api.port)

    async def _serve_api(self, server) -> None:
        """Keep Uvicorn's SystemExit startup failure inside the owned task."""
        try:
            await server.serve()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._api_startup_exception = exc

    async def _wait_for_api_ready(self, server, task: asyncio.Task) -> None:
        """Wait for Uvicorn's actual bind/start barrier, not task creation."""
        while not server.started:
            if task.done():
                if self._api_startup_exception is not None:
                    raise RuntimeError("API server failed during startup") from self._api_startup_exception
                try:
                    task.result()
                except asyncio.CancelledError as exc:
                    raise RuntimeError("API server task was cancelled during startup") from exc
                except BaseException as exc:
                    raise RuntimeError("API server failed during startup") from exc
                raise RuntimeError("API server exited before startup")
            await asyncio.sleep(0.01)

    async def _on_adapter_connection(self, connected: bool) -> None:
        notifier = self._realtime
        if notifier is None:
            return
        await notifier.publish(
            "connection.updated",
            {
                "adapter_id": f"onebot:{self.config.onebot.host}:{self.config.onebot.port}",
                "connected": connected,
            },
        )

    async def _fire_reminder(self, reminder_id: int) -> None:
        """Scheduler fire handler -> ReminderService.fire (re-checks latest
        DB state; redacted logging; never raises out of the scheduler)."""
        try:
            rs = getattr(self, "_reminder_service", None)
            if rs is not None:
                await rs.fire(reminder_id)
        except Exception:
            logger.exception("reminder fire failed; reminder_id=%s", reminder_id)

    async def _route_event(self, event) -> None:
        """Bus handler: route, then send inside the handler so the EventBus
        concurrency bound covers the full pipeline. Send failures are caught
        and logged redacted (they never escape as unretrieved task exceptions)."""
        if self.router is None:
            return
        try:
            result = await self.router.route(event)
            if result is not None and self.adapter is not None:
                await self.adapter.send(result)
        except ActionFailure as e:
            logger.warning(
                "outbound send failed; trace=%s error=%s", event.trace_id[:8], e
            )
        except Exception:
            logger.exception("event pipeline failed; trace=%s", event.trace_id[:8])

    async def _cleanup_after_failure(self) -> None:
        if self._api_server is not None:
            try:
                self._api_server.should_exit = True
                if self._api_task is not None:
                    await asyncio.wait_for(self._api_task, 3.0)
            except BaseException:
                if self._api_task is not None:
                    self._api_task.cancel()
                    try:
                        await self._api_task
                    except BaseException:
                        pass
            self._api_server = None
            self._api_task = None
        if self._api_log_handler is not None:
            logging.getLogger("campuscue").removeHandler(self._api_log_handler)
            self._api_log_handler = None
        if self.adapter is not None:
            try:
                await self.adapter.stop()
            except Exception:
                pass
        if self.bus is not None:
            try:
                await self.bus.shutdown(timeout_s=1.0)
            except Exception:
                pass
        rs = getattr(self, "_reminder_scheduler", None)
        if rs is not None:
            try:
                await rs.shutdown(wait=False)
            except Exception:
                pass
            self._reminder_scheduler = None
        await self._dispose_database()

    async def _dispose_database(self) -> None:
        if self._database is not None:
            try:
                await self._database.dispose()
            except Exception:
                pass
            self._database = None

    async def stop(self) -> None:
        if self.state in (RuntimeState.STOPPED, RuntimeState.FAILED, RuntimeState.CREATED):
            return
        self.state = RuntimeState.STOPPING
        # 0) stop API first (no new HTTP/SSE; close owned API task)
        if self._api_server is not None:
            try:
                self._api_server.should_exit = True
                if self._api_task is not None:
                    await asyncio.wait_for(self._api_task, 5.0)
            except BaseException:
                if self._api_task is not None:
                    self._api_task.cancel()
                    try:
                        await self._api_task
                    except BaseException:
                        pass
            self._api_server = None
            self._api_task = None
        if self._api_log_handler is not None:
            logging.getLogger("campuscue").removeHandler(self._api_log_handler)
            self._api_log_handler = None
        # 1) stop accepting new ingress (close WS server + active connection)
        if self.adapter is not None:
            await self.adapter.stop()
        # 2) bounded drain of in-flight handlers
        if self.bus is not None:
            await self.bus.shutdown(timeout_s=3.0)
        # 2b) stop ReminderScheduler cleanly (wait in-flight fire handlers;
        #     no orphan background work — M3 §17)
        rs = getattr(self, "_reminder_scheduler", None)
        if rs is not None:
            try:
                await rs.shutdown(wait=True)
            except Exception:
                logger.exception("reminder scheduler shutdown failed")
            self._reminder_scheduler = None
        # 3) dispose owned DB (M2 opt-in)
        await self._dispose_database()
        self.state = RuntimeState.STOPPED
        logger.info("campus runtime STOPPED")
