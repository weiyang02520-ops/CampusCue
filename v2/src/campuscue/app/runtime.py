"""CampusRuntime - M1 composition root.

State machine: CREATED -> STARTING -> RUNNING -> STOPPING -> STOPPED | FAILED.
M1 wires only: Config, EchoHandler, Router, EventBus, OneBotAdapter.
No DB / Provider / Reminder / Agent / API (M2+).
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum

from campuscue.adapters.onebot.adapter import OneBotAdapter
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
        self._owned_tasks: set[asyncio.Task[None]] = set()
        self._outbound_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.state = RuntimeState.STARTING
        try:
            # wiring order matters: handlers/router ready before events flow (no startup race)
            self.router = Router()
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

    async def _route_event(self, event) -> None:
        """Bus handler: route event, then send the outbound result directly (no outbound bus)."""
        if self.router is None:
            return
        result = await self.router.route(event)
        if result is not None and self.adapter is not None:
            task = asyncio.create_task(self.adapter.send(result), name=f"outbound.{event.event_id[:8]}")
            self._owned_tasks.add(task)
            task.add_done_callback(self._owned_tasks.discard)

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
        # 3) cancel owned outbound tasks
        if self._outbound_task is not None and not self._outbound_task.done():
            self._outbound_task.cancel()
        if self._owned_tasks:
            for t in list(self._owned_tasks):
                t.cancel()
        self.state = RuntimeState.STOPPED
        logger.info("campus runtime STOPPED")
