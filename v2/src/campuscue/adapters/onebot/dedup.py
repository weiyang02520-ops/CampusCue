"""Transport-level dedup: bounded TTL cache keyed on (self_id, message_id).

Purpose: protect against duplicate delivery / reconnects re-reporting the same
message. This is transport idempotency, NOT M2 task semantic dedup.
Canonical enforcement point: OneBot Adapter ingress, AFTER converter, BEFORE
bus.publish (the Router never re-invokes this stateful deduper).
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TransportDedup:
    def __init__(self, ttl_s: float = 300.0, capacity: int = 10000, clock: Clock | None = None) -> None:
        self._ttl_s = ttl_s
        self._capacity = capacity
        self._clock = clock or utcnow
        self._cache: OrderedDict[tuple[str, str], float] = OrderedDict()

    def check_and_add(self, self_id: str, message_id: str) -> bool:
        """Returns True if this key is new (should be processed), False if duplicate."""
        if not message_id:
            return True  # no message_id -> cannot dedup; process
        key = (self_id, message_id)
        now = self._clock().timestamp()
        self._evict(now)
        if key in self._cache:
            return False
        self._cache[key] = now
        self._trim(now)
        return True

    def _evict(self, now: float) -> None:
        expired = [k for k, ts in self._cache.items() if now - ts > self._ttl_s]
        for k in expired:
            del self._cache[k]

    def _trim(self, now: float) -> None:
        while len(self._cache) > self._capacity:
            self._cache.popitem(last=False)

    def __len__(self) -> int:
        return len(self._cache)
