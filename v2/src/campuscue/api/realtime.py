"""Realtime SSE hub (M5).

Notification-only, no replay. Each subscriber gets its own bounded queue; a
slow subscriber that overflows is disconnected instead of blocking business
mutations.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any, AsyncIterator

from campuscue.core.realtime import RealtimeEvent, RealtimeNotifier

DEFAULT_QUEUE_SIZE = 32
HEARTBEAT_INTERVAL_S = 15.0


class RealtimeHub(RealtimeNotifier):
    def __init__(self, *, queue_size: int = DEFAULT_QUEUE_SIZE) -> None:
        if queue_size <= 0:
            raise ValueError("queue_size must be > 0")
        self._queue_size = queue_size
        self._subscribers: dict[int, asyncio.Queue[RealtimeEvent]] = {}
        self._seq = itertools.count(1)

    def subscribe(self) -> tuple[int, asyncio.Queue[RealtimeEvent]]:
        sub_id = next(self._seq)
        queue: asyncio.Queue[RealtimeEvent] = asyncio.Queue(maxsize=self._queue_size)
        self._subscribers[sub_id] = queue
        return sub_id, queue

    def unsubscribe(self, sub_id: int) -> None:
        self._subscribers.pop(sub_id, None)

    def subscriber_count(self) -> int:
        return len(self._subscribers)

    async def publish(self, event: str, data: dict[str, Any]) -> None:
        seq = next(self._seq)
        ev = RealtimeEvent(event=event, data=data, sequence=seq)
        stale: list[int] = []
        for sub_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(ev)
            except asyncio.QueueFull:
                # Slow subscriber: disconnect it; the client can reconnect and
                # REST-refresh canonical state. Never block the publisher.
                stale.append(sub_id)
        for sub_id in stale:
            self.unsubscribe(sub_id)

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
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval_s)
                    yield self.format_sse(event)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            self.unsubscribe(sub_id)
