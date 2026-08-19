"""Bounded in-memory redacted diagnostic log ring buffer (M5)."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import Any


class LogBuffer:
    def __init__(self, maxlen: int = 200) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)

    def add(self, *, level: str, component: str, message: str) -> None:
        self._items.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": level,
                "component": component,
                "message": message,
            }
        )

    def list(self, *, level: str | None = None, component: str | None = None, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        rows = list(self._items)
        if level:
            rows = [r for r in rows if r["level"].lower() == level.lower()]
        if component:
            rows = [r for r in rows if component.lower() in r["component"].lower()]
        rows.reverse()
        return rows[offset:offset + limit]

    def total(self, *, level: str | None = None, component: str | None = None) -> int:
        rows = list(self._items)
        if level:
            rows = [r for r in rows if r["level"].lower() == level.lower()]
        if component:
            rows = [r for r in rows if component.lower() in r["component"].lower()]
        return len(rows)


class LogBufferHandler(logging.Handler):
    def __init__(self, buffer: LogBuffer) -> None:
        super().__init__()
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._buffer.add(
                level=record.levelname,
                component=record.name,
                message=self.format(record),
            )
        except Exception:
            pass
