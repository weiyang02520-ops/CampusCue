"""Realtime notification contract (M5).

Services depend on this small protocol, never on the API/SSE package. The
concrete RealtimeHub in ``campuscue.api.realtime`` implements it. When no
notifier is injected (M1-M4 / M5 disabled), services behave exactly as before.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RealtimeEvent:
    event: str
    data: dict[str, Any]
    sequence: int = 0


class RealtimeNotifier(ABC):
    """Async publisher of short, redacted change notifications."""

    @abstractmethod
    async def publish(self, event: str, data: dict[str, Any]) -> None:
        """Publish one event to all subscribers.

        Implementations MUST NOT block the caller on a slow subscriber; they
        should drop/expire stale subscribers instead.
        """
