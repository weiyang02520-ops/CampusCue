"""Realtime SSE hub (M5).

Notification-only, no replay. Each subscriber gets its own bounded queue; a
slow subscriber that overflows is disconnected instead of blocking business
mutations.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

from campuscue.core.realtime import RealtimeEvent, RealtimeNotifier

DEFAULT_QUEUE_SIZE = 32
HEARTBEAT_INTERVAL_S = 15.0


class RealtimeHub(RealtimeNotifier):
    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be > 0")
        self._queue_size = queue_size
        self._subscribers: dict[int, _Subscriber] = {}
        self._seq = itertools.count(1)

    def subscribe(self) -> tuple[int, asyncio.Queue[RealtimeEvent]]:
        sub_id = next(self._seq)
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[sub_id] = _Subscriber(sub_id=sub_id, queue=queue)
        return sub_id, queue

    def unsubscribe(self, sub_id: int, *, reason: str = "client disconnected") -> None:
        subscriber = self._subscribers.pop(sub_id, None)
        if subscriber is not None:
            subscriber.close(reason)

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        seq = next(self._seq)
        ev = RealtimeEvent(event=event, data=data, sequence=seq)
        stale: list[int] = []
        for sub_id, subscriber in list(self._subscribers.items()):
            try:
                subscriber.queue.put_nowait(ev)
            except asyncio.QueueFull:
                # Slow subscriber: disconnect it; the client can reconnect and
                # REST-refresh canonical state. Never block the publisher.
                stale.append(sub_id)
            except Exception:
                # A subscriber is a derived transport boundary. A broken
                # subscriber must never make a committed business mutation
                # fail or block other subscribers.
                stale.append(sub_id)
        for sub_id in stale:
            self.unsubscribe(sub_id, reason="subscriber queue unavailable")

    def format_sse(self, event: RealtimeEvent) -> str:
        payload = {"sequence": event.sequence, **event.data}
        return f"event: {event.event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def stream(
        self,
        sub_id: int,
        queue: asyncio.Queue[RealtimeEvent],
        *,
        heartbeat_interval_s: float = HEARTBEAT_INTERVAL_S,
    ) -> AsyncIterator[str]:
        subscriber = self._subscribers.get(sub_id)
        if subscriber is None or subscriber.queue is not queue:
            # The subscriber may have overflowed before the HTTP generator
            # started. It is already closed and must not become a ghost stream.
            return
        try:
            while True:
                if subscriber.closed.is_set():
                    return
                queue_task = asyncio.create_task(queue.get())
                closed_task = asyncio.create_task(subscriber.closed.wait())
                done, pending = await asyncio.wait(
                    (queue_task, closed_task),
                    timeout=heartbeat_interval_s,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                if not done:
                    yield ": ping\n\n"
                    continue
                if closed_task in done:
                    return
                event = queue_task.result()
                yield self.format_sse(event)
        finally:
            self.unsubscribe(sub_id, reason="stream closed")


@dataclass
class _Subscriber:
    sub_id: int
    queue: asyncio.Queue[RealtimeEvent]
    closed: asyncio.Event
    close_reason: str | None = None

    def __init__(self, *, sub_id: int, queue: asyncio.Queue[RealtimeEvent]) -> None:
        self.sub_id = sub_id
        self.queue = queue
        self.closed = asyncio.Event()
        self.close_reason = None

    def close(self, reason: str) -> None:
        self.close_reason = reason
        self.closed.set()
