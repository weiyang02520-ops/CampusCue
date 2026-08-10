"""Tiny clock abstraction (M2): deterministic tests, no datetime.now() scatter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Protocol


class Clock(Protocol):
    def utcnow(self) -> datetime: ...


class SystemClock:
    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """Deterministic clock for tests."""

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)

    def utcnow(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        from datetime import timedelta

        self._now = self._now + timedelta(seconds=seconds)


ClockFactory = Callable[[], Clock]
