"""Router - minimal M1 routing.

M1: validate event type, stateless self-message defense-in-depth, select handler.
No SourcePolicy / Task / Agent routing (M2+).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from campuscue.core.events import CampusEvent
from campuscue.core.outbound import OutgoingMessage

RouterResult = OutgoingMessage | None
RouteHandler = Callable[[CampusEvent], Awaitable[RouterResult]]


class Router:
    def __init__(self) -> None:
        self._handlers: list[RouteHandler] = []

    def add_handler(self, handler: RouteHandler) -> None:
        self._handlers.append(handler)

    async def route(self, event: CampusEvent) -> RouterResult:
        """Route an event to the first matching handler. Returns None when unhandled."""
        if not event.is_message:
            return None
        if event.sender_id == event.self_id:
            # stateless defense-in-depth; canonical suppression lives in the Adapter
            return None
        for handler in self._handlers:
            result = await handler(event)
            if result is not None:
                return result
        return None
