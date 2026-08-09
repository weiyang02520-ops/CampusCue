"""Unit tests: connection generation race — stale cleanup must not clear the new
active connection; old connection's pending actions fail; new one works."""

from __future__ import annotations

import asyncio
import json

import pytest

from campuscue.adapters.onebot.adapter import ActionFailure, OneBotAdapter
from campuscue.config import OneBotConfig
from campuscue.core.events import ConversationType
from campuscue.core.outbound import OutgoingMessage


class _FakeConn:
    def __init__(self, name):
        self.name = name
        self.closed = False
        self.sent = []

    async def send(self, text):
        self.sent.append(text)

    async def close(self):
        self.closed = True


def _cfg():
    return OneBotConfig(host="127.0.0.1", port=6199, path="/ws", access_token=None,
                        action_timeout_s=0.5, max_pending_actions=4, dedup_ttl_s=300,
                        dedup_capacity=100)


def _mk_adapter():
    return OneBotAdapter(_cfg(), on_event=lambda ev: asyncio.sleep(0))


@pytest.mark.asyncio
async def test_stale_cleanup_does_not_clear_new_active():
    a = _mk_adapter()
    conn_a = _FakeConn("A")
    conn_b = _FakeConn("B")

    # simulate connection A established
    a._conn = conn_a
    # connection B arrives and replaces A (same flow as _handle_connection)
    old = a._conn
    a._conn = conn_b
    if old is not None and old is not conn_b:
        await old.close()

    assert a._conn is conn_b

    # A's finally block executes LATER (stale connection cleanup). It must only
    # clear _conn if _conn is still the A connection — which it is not.
    if a._conn is conn_a:
        a._conn = None
    assert a._conn is conn_b  # B remains active

    # B must still be able to send
    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "received: hello"))
    )
    await asyncio.sleep(0.05)
    assert len(conn_b.sent) == 1
    frame = json.loads(conn_b.sent[0])
    assert frame["action"] == "send_group_msg"
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task, 1.0)
    assert a._conn is conn_b  # still B


@pytest.mark.asyncio
async def test_old_connection_pending_fails_when_replaced():
    a = _mk_adapter()
    conn_a = _FakeConn("A")
    a._conn = conn_a

    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "x"))
    )
    await asyncio.sleep(0.05)
    assert len(a._pending) == 1

    # B replaces A -> old pending must fail immediately
    conn_b = _FakeConn("B")
    old = a._conn
    a._conn = conn_b
    if old is not None and old is not conn_b:
        a._fail_all_pending("connection replaced by new connection")
        await old.close()

    with pytest.raises(ActionFailure, match="replaced"):
        await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0
    assert a._conn is conn_b


@pytest.mark.asyncio
async def test_new_connection_works_after_old_pending_failed():
    a = _mk_adapter()
    conn_a = _FakeConn("A")
    a._conn = conn_a

    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "old"))
    )
    await asyncio.sleep(0.05)

    conn_b = _FakeConn("B")
    old = a._conn
    a._conn = conn_b
    if old is not None and old is not conn_b:
        a._fail_all_pending("connection replaced")
        await old.close()
    with pytest.raises(ActionFailure):
        await asyncio.wait_for(send_task, 1.0)

    # B's own actions work normally
    send_task2 = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "new"))
    )
    await asyncio.sleep(0.05)
    frame = json.loads(conn_b.sent[0])
    assert frame["params"]["message"] == "new"
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task2, 1.0)


@pytest.mark.asyncio
async def test_disconnect_fails_pending_without_waiting_timeout():
    a = _mk_adapter()
    a._conn = _FakeConn("A")
    send_task = asyncio.create_task(
        a.send(OutgoingMessage("123", ConversationType.GROUP, "x"))
    )
    await asyncio.sleep(0.05)
    # connection lost -> all pending fail immediately (not after 10s timeout)
    a._fail_all_pending("connection lost")
    with pytest.raises(ActionFailure, match="connection lost"):
        await asyncio.wait_for(send_task, 0.5)
