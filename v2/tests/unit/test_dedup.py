"""Unit tests: transport dedup (bounded TTL cache, testable clock)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from campuscue.adapters.onebot.dedup import TransportDedup


class _FakeClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now = self.now + timedelta(seconds=seconds)


def _clock(start=None):
    return _FakeClock(start or datetime(2026, 8, 9, 0, 0, 0, tzinfo=timezone.utc))


class TestDedup:
    def test_first_accepted(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True

    def test_duplicate_rejected(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True
        assert d.check_and_add("10001", "m1") is False

    def test_after_ttl_accepted_again(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True
        c.advance(301)
        assert d.check_and_add("10001", "m1") is True

    def test_capacity_bounded(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=3, clock=c)
        assert d.check_and_add("10001", "a") is True
        assert d.check_and_add("10001", "b") is True
        assert d.check_and_add("10001", "c") is True
        assert d.check_and_add("10001", "d") is True  # evicts oldest (a)
        assert len(d) == 3
        # b/c/d still cached -> duplicates; a was evicted -> accepted again
        assert d.check_and_add("10001", "b") is False
        assert d.check_and_add("10001", "c") is False
        assert d.check_and_add("10001", "d") is False
        assert d.check_and_add("10001", "a") is True

    def test_different_self_id_same_message_id_not_duplicate(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True
        assert d.check_and_add("10002", "m1") is True

    def test_different_message_id_not_duplicate(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True
        assert d.check_and_add("10001", "m2") is True

    def test_empty_message_id_always_accepted(self):
        c = _clock()
        d = TransportDedup(ttl_s=300, capacity=100, clock=c)
        assert d.check_and_add("10001", "") is True
        assert d.check_and_add("10001", "") is True

    def test_ttl_eviction_uses_clock(self):
        c = _clock()
        d = TransportDedup(ttl_s=10, capacity=100, clock=c)
        assert d.check_and_add("10001", "m1") is True
        c.advance(11)
        # eviction happens on next operation
        assert d.check_and_add("10001", "m2") is True
        assert d.check_and_add("10001", "m1") is True  # m1 expired
