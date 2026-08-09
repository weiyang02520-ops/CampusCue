"""M1.1 regression tests: connection lifecycle race (finding A) through the REAL
`_handle_connection` path, plus pending-action backpressure (finding C).

Rule (M1.1 §10): never test a hand-copied half of the production code — drive
the real internal path wherever possible.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from campuscue.adapters.onebot.adapter import ActionFailure, OneBotAdapter
from campuscue.config import OneBotConfig
from campuscue.core.events import ConversationType
from campuscue.core.outbound import OutgoingMessage


class _LiveConn:
    """A real-ish connection object whose recv loop we can drive by hand while
    still going through OneBotAdapter._handle_connection's real finally."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False
        self.name = "live"
        self._stop = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._stop:
            raise StopAsyncIteration
        try:
            item = await asyncio.wait_for(self.recv(), 5.0)
        except asyncio.TimeoutError:
            raise StopAsyncIteration
        if self._stop:
            raise StopAsyncIteration
        return item

    async def recv(self):
        return await self._queue.get()

    async def send(self, text):
        self.sent.append(text)

    async def close(self):
        self.closed = True

    def feed(self, frame: str):
        self._queue.put_nowait(frame)

    def stop_loop(self):
        """Stop the recv loop and wake a blocked recv."""
        self._stop = True
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass


def _cfg(**kw):
    base = dict(host="127.0.0.1", port=6199, path="/ws", access_token=None,
                action_timeout_s=2.0, max_pending_actions=4, dedup_ttl_s=300,
                dedup_capacity=100)
    base.update(kw)
    return OneBotConfig(**base)


def _mk_adapter(**cfg_kw) -> OneBotAdapter:
    return OneBotAdapter(_cfg(**cfg_kw), on_event=lambda ev: asyncio.sleep(0))


def _hello_payload(seq: int) -> str:
    return json.dumps({
        "post_type": "message",
        "self_id": 10001,
        "message_id": 5000 + seq,
        "message_type": "group",
        "group_id": 123,
        "sender": {"user_id": 555, "nickname": "x"},
        "time": 1723200000 + seq,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    })


@pytest.mark.asyncio
async def test_stale_finally_does_not_fail_new_pending_real_path():
    """A active -> B replaces A -> B has unresolved pending -> A's delayed
    finally runs -> B's pending MUST survive and resolve via matching echo.

    Drives the real _handle_connection loop for both connections.
    """
    a = _mk_adapter()
    conn_a = _LiveConn()
    conn_b = _LiveConn()
    a._conn = conn_a

    # start A's real connection loop (its finally will run later, at cleanup)
    task_a = asyncio.create_task(a._handle_connection(conn_a), name="conn-a")

    # start B's real connection loop -> replaces A inside _handle_connection
    task_b = asyncio.create_task(a._handle_connection(conn_b), name="conn-b")
    await asyncio.sleep(0.05)
    assert a._conn is conn_b

    # B creates an unresolved pending action (no response yet)
    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "received: hello"))
    )
    await asyncio.sleep(0.05)
    assert len(a._pending) == 1
    frame_b = json.loads(conn_b.sent[0])
    assert frame_b["action"] == "send_group_msg"

    # A's connection dies now; its real finally executes while B still has pending
    conn_a.stop_loop()
    await asyncio.sleep(0.05)

    # B's pending must still be alive
    assert len(a._pending) == 1
    assert not send_task.done()

    # B's matching response resolves it
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame_b["echo"]})
    await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0

    # cleanup
    conn_b.stop_loop()
    await asyncio.sleep(0.05)
    await task_a
    await task_b


@pytest.mark.asyncio
async def test_disconnect_fails_own_pending_real_path():
    a = _mk_adapter()
    conn = _LiveConn()
    a._conn = conn
    task = asyncio.create_task(a._handle_connection(conn), name="conn")

    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "x"))
    )
    await asyncio.sleep(0.05)
    assert len(a._pending) == 1

    # genuine disconnect of the ACTIVE connection: its finally fails its pending
    conn.stop_loop()
    with pytest.raises(ActionFailure, match="connection lost"):
        await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0
    assert a._conn is None
    await task


@pytest.mark.asyncio
async def test_pending_backpressure_waits_not_errors():
    """max_pending_actions=1: action B must WAIT for A, then proceed."""
    a = _mk_adapter(max_pending_actions=1)
    conn = _LiveConn()
    a._conn = conn

    # A: unresolved pending action (occupies the single slot)
    task_a = asyncio.create_task(
        a.send(OutgoingMessage("1", ConversationType.GROUP, "A"))
    )
    await asyncio.sleep(0.05)
    assert len(a._pending) == 1
    frame_a = json.loads(conn.sent[0])

    # B: must wait (backpressure), NOT raise a limit error
    task_b = asyncio.create_task(
        a.send(OutgoingMessage("2", ConversationType.GROUP, "B"))
    )
    await asyncio.sleep(0.05)
    assert not task_b.done()
    assert len(conn.sent) == 1  # B not sent yet

    # A resolves -> B proceeds
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame_a["echo"]})
    await asyncio.wait_for(task_a, 1.0)
    await asyncio.sleep(0.05)
    assert len(conn.sent) == 2
    frame_b = json.loads(conn.sent[1])
    assert frame_b["params"]["message"] == "B"
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame_b["echo"]})
    await asyncio.wait_for(task_b, 1.0)


@pytest.mark.asyncio
async def test_pending_semaphore_released_on_cancellation():
    """A cancelled send must release its slot (no leak)."""
    a = _mk_adapter(max_pending_actions=1)
    conn = _LiveConn()
    a._conn = conn

    task = asyncio.create_task(
        a.send(OutgoingMessage("1", ConversationType.GROUP, "A"))
    )
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.05)
    # slot is free again: a new send proceeds (would hang forever if leaked)
    task2 = asyncio.create_task(
        a.send(OutgoingMessage("2", ConversationType.GROUP, "B"))
    )
    await asyncio.sleep(0.05)
    # first send went out before cancellation; task2's send also went through
    # -> the cancelled task released its slot (would hang if leaked)
    assert len(conn.sent) == 2
    frame2 = json.loads(conn.sent[1])
    assert frame2["params"]["message"] == "B"
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame2["echo"]})
    await asyncio.wait_for(task2, 1.0)
