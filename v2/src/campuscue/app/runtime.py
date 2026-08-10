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
            )
            await self.adapter.start()
            self.state = RuntimeState.RUNNING
            logger.info("campus runtime RUNNING")
        except Exception as e:
            logger.exception("runtime startup failed: %s", e)
            await self._cleanup_after_failure()
            self.state = RuntimeState.FAILED
            raise

    async def _init_task_pipeline(self) -> None:
        """M2 opt-in wiring: DB + repositories + services + pipeline handler.
        Pipeline handler is added BEFORE EchoHandler so hello still reaches Echo."""
        from zoneinfo import ZoneInfo

        import os as _os

        from campuscue.providers.manager import ProviderManager
        from campuscue.repositories.repositories import (
            ExtractionRepository,
            ProviderConfigRepository,
            SourceRepository,
            TaskRepository,
        )
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
        await database.initialize()
        self._database = database
        sf = database.session
        task_service = TaskService(
            TaskRepository(sf), confidence_threshold=self.config.tasks.confidence_threshold
        )
        pipeline = TaskPipeline(
            sources=SourceRepository(sf),
            extractions=ExtractionRepository(sf),
            task_service=task_service,
            provider_manager=ProviderManager(ProviderConfigRepository(sf)),
            timezone=ZoneInfo(self.config.tasks.timezone),
            confidence_threshold=self.config.tasks.confidence_threshold,
        )
        self._pipeline = pipeline
        self.router.add_handler(pipeline.handle)

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
        # 1) stop accepting new ingress (close WS server + active connection)
        if self.adapter is not None:
            await self.adapter.stop()
        # 2) bounded drain of in-flight handlers
        if self.bus is not None:
            await self.bus.shutdown(timeout_s=3.0)
        # 3) dispose owned DB (M2 opt-in)
        await self._dispose_database()
        self.state = RuntimeState.STOPPED
        logger.info("campus runtime STOPPED")
