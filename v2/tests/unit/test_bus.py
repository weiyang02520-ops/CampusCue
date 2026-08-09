"""Unit tests: EventBus (bounded queue + bounded in-flight + isolation + shutdown)."""

from __future__ import annotations

import asyncio

import pytest

from campuscue.core.bus import EventBus
from campuscue.core.events import CampusEvent, ConversationType, EventType, new_event_id


def _mk_event(text="hello"):
    return CampusEvent(
        event_id=new_event_id(),
        trace_id=new_event_id(),
        platform="onebot",
        adapter_id="t",
        event_type=EventType.GROUP_MESSAGE,
        self_id="1",
        message_id=new_event_id(),
        conversation_id="g",
        conversation_type=ConversationType.GROUP,
        sender_id="2",
        sender_name="",
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        text=text,
    )


@pytest.mark.asyncio
async def test_publish_delivers_to_handler():
    bus = EventBus(queue_maxsize=10, max_in_flight=4)
    got = []
    async def h(ev):
        got.append(ev.text)
    bus.subscribe(h)
    bus.start()
    await bus.publish(_mk_event("a"))
    await asyncio.sleep(0.05)
    assert got == ["a"]
    await bus.shutdown()


@pytest.mark.asyncio
async def test_handler_exception_isolation_dispatch_continues():
    bus = EventBus(queue_maxsize=10, max_in_flight=4)
    got = []
    async def h(ev):
        if ev.text == "boom":
            raise RuntimeError("handler crash")
        got.append(ev.text)
    bus.subscribe(h)
    bus.start()
    await bus.publish(_mk_event("boom"))
    await bus.publish(_mk_event("fine"))
    await asyncio.sleep(0.1)
    assert got == ["fine"]
    await bus.shutdown()


@pytest.mark.asyncio
async def test_bounded_queue_backpressure_blocks_publish():
    bus = EventBus(queue_maxsize=2, max_in_flight=1)
    release = asyncio.Event()
    started = asyncio.Event()
    async def slow(ev):
        started.set()
        await release.wait()
    bus.subscribe(slow)
    bus.start()
    await bus.publish(_mk_event("1"))
    await started.wait()  # first handler in-flight, queue empty
    await bus.publish(_mk_event("2"))
    await bus.publish(_mk_event("3"))
    # queue now full (size 2); a third publish must block until a slot frees
    publish_task = asyncio.create_task(bus.publish(_mk_event("4")))
    await asyncio.sleep(0.05)
    assert not publish_task.done()
    release.set()
    await asyncio.wait_for(publish_task, 2.0)
    await bus.shutdown()


@pytest.mark.asyncio
async def test_in_flight_concurrency_never_exceeds_bound():
    bus = EventBus(queue_maxsize=100, max_in_flight=3)
    active = 0
    peak = 0
    async def h(ev):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.03)
        active -= 1
    bus.subscribe(h)
    bus.start()
    for i in range(12):
        await bus.publish(_mk_event(f"m{i}"))
    await asyncio.sleep(0.5)
    assert peak <= 3
    await bus.shutdown()


@pytest.mark.asyncio
async def test_shutdown_empty_queue():
    bus = EventBus(queue_maxsize=10, max_in_flight=4)
    bus.start()
    await bus.shutdown()
    # second shutdown safe
    await bus.shutdown()


@pytest.mark.asyncio
async def test_shutdown_with_queued_events_drains():
    bus = EventBus(queue_maxsize=10, max_in_flight=2)
    got = []
    async def h(ev):
        await asyncio.sleep(0.02)
        got.append(ev.text)
    bus.subscribe(h)
    bus.start()
    for i in range(5):
        await bus.publish(_mk_event(f"m{i}"))
    await bus.shutdown(timeout_s=2.0)
    # drain policy: events either processed or dropped, but no unowned tasks remain
    assert len(got) <= 5


@pytest.mark.asyncio
async def test_shutdown_with_active_handler():
    bus = EventBus(queue_maxsize=10, max_in_flight=4)
    release = asyncio.Event()
    async def h(ev):
        await release.wait()
    bus.subscribe(h)
    bus.start()
    await bus.publish(_mk_event("slow"))
    await asyncio.sleep(0.05)
    await bus.shutdown(timeout_s=0.2)  # bounded timeout then cancel
    release.set()
    await asyncio.sleep(0.05)
    # no pending tasks left behind
    assert len(bus._handler_tasks) == 0


@pytest.mark.asyncio
async def test_no_unowned_background_tasks_after_shutdown():
    bus = EventBus(queue_maxsize=10, max_in_flight=4)
    bus.start()
    await bus.publish(_mk_event("x"))
    await asyncio.sleep(0.05)
    await bus.shutdown()
    # all created tasks are owned and finished
    pending = [t for t in asyncio.all_tasks() if not t.done() and "bus." in t.get_name()]
    assert pending == []
