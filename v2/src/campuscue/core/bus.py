"""EventBus - bounded inbound pipeline.

Bounded queue + bounded in-flight handler concurrency (M1 requirement):
both can never grow unbounded. Every handler runs in its own owned task;
an exception in one handler never kills the dispatch loop.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from campuscue.core.events import CampusEvent

logger = logging.getLogger("campuscue.bus")

Handler = Callable[[CampusEvent], Awaitable[None] | None]


class EventBus:
    def __init__(self, queue_maxsize: int = 256, max_in_flight: int = 32) -> None:
        self._queue: asyncio.Queue[CampusEvent] = asyncio.Queue(maxsize=queue_maxsize)
        self._max_in_flight = max_in_flight
        self._semaphore = asyncio.Semaphore(max_in_flight)
        self._dispatch_task: asyncio.Task[None] | None = None
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._handlers: list[Handler] = []

    async def publish(self, event: CampusEvent) -> None:
        """Enqueue an event; awaits when the queue is saturated (backpressure)."""
        await self._queue.put(event)

    def start(self) -> None:
        if self._dispatch_task is not None and not self._dispatch_task.done():
            return
        self._dispatch_task = asyncio.create_task(self._dispatch_loop(), name="bus.dispatch")

    async def _dispatch_loop(self) -> None:
        while True:
            # bound in-flight FIRST: items stay queued until a handler slot frees,
            # so publish() blocks exactly when the queue is full (backpressure)
            await self._semaphore.acquire()
            try:
                event = await self._queue.get()
            except asyncio.CancelledError:
                self._semaphore.release()
                raise
            task = asyncio.create_task(
                self._run_handler(event, self._semaphore),
                name=f"bus.handler.{event.event_id[:8]}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._handler_tasks.discard)

    async def _run_handler(self, event: CampusEvent, semaphore: asyncio.Semaphore) -> None:
        try:
            for handler in self._handlers:
                try:
                    result = handler(event)
                    if result is not None:
                        await result
                except Exception:
                    logger.exception(
                        "handler failed; event_id=%s trace=%s", event.event_id[:8], event.trace_id[:8]
                    )
        finally:
            semaphore.release()

    def subscribe(self, handler: Handler) -> None:
        self._handlers.append(handler)

    async def shutdown(self, timeout_s: float = 5.0) -> None:
        """Stop accepting new events, drain/cancel in-flight, cancel dispatch."""
        if self._dispatch_task is None:
            return
        self._dispatch_task.cancel()
        await self._safe_wait(self._dispatch_task, timeout_s)
        # drain queue without processing
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        if self._handler_tasks:
            await self._safe_wait_all(list(self._handler_tasks), timeout_s)

    @staticmethod
    async def _safe_wait(task: asyncio.Task[None], timeout_s: float) -> None:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout_s)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            task.cancel()

    @staticmethod
    async def _safe_wait_all(tasks: list[asyncio.Task[None]], timeout_s: float) -> None:
        done, pending = await asyncio.wait(tasks, timeout=timeout_s)
        for t in pending:
            t.cancel()
