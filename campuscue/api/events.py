"""In-process pub/sub so the board updates the moment an extraction lands.

This is the three seconds the demo video is built around: a message appears in
the group and the card materialises on screen without anyone touching the page.
Polling would work, but a poll interval is visible as a lag on stage, and "it
just appeared" is the whole point of a proactive assistant.

Server-sent events rather than websockets: the traffic is one-directional, SSE
survives proxies that mangle upgrades, and browsers reconnect on their own.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from astrbot.core import logger

QUEUE_SIZE = 64
"""Per-subscriber buffer. A browser tab that stops reading (laptop asleep,
throttled background tab) must not grow a queue without bound; once full, the
oldest events are dropped and the client refetches on reconnect."""


class EventHub:
    """Fan out task events to every connected board."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def publish(self, event: str, payload: Any) -> None:
        """Broadcast one event. Never blocks and never raises.

        Called from the extraction pipeline, which must not slow down or fail
        because a browser tab is unresponsive.
        """
        if not self._subscribers:
            return
        try:
            body = json.dumps(
                {"event": event, "data": payload},
                ensure_ascii=False,
                default=str,
            )
        except (TypeError, ValueError):
            logger.warning("[campuscue] unserialisable SSE payload for %s", event)
            return

        for queue in list(self._subscribers):
            try:
                queue.put_nowait(body)
            except asyncio.QueueFull:
                # Drop the oldest rather than the newest: a board showing stale
                # cards is worse than one that missed an intermediate update,
                # and the client refetches the full list on reconnect.
                try:
                    queue.get_nowait()
                    queue.put_nowait(body)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


hub = EventHub()
"""Process-wide hub. A single-process local deployment is the design target; a
multi-worker deployment would need a real broker, which the MVP does not."""


__all__ = ["EventHub", "QUEUE_SIZE", "hub"]
