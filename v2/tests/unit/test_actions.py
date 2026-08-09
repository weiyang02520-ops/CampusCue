"""Unit tests: outbound action echo correlation (pending futures)."""

from __future__ import annotations

import asyncio
import json

import pytest

from campuscue.adapters.onebot.adapter import ActionFailure, OneBotAdapter
from campuscue.adapters.onebot.protocol import build_action
from campuscue.config import OneBotConfig
from campuscue.core.events import ConversationType
from campuscue.core.outbound import OutgoingMessage


class _FakeConn:
    """Minimal stand-in for ServerConnection.send/close."""

    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send(self, text: str):
        self.sent.append(text)

    async def close(self):
        self.closed = True


def _cfg(**kw):
    base = dict(host="127.0.0.1", port=6199, path="/ws", access_token=None,
                action_timeout_s=0.5, max_pending_actions=4, dedup_ttl_s=300, dedup_capacity=100)
    base.update(kw)
    return OneBotConfig(**base)


async def _make_adapter(**cfg_kw) -> OneBotAdapter:
    from campuscue.adapters.onebot.adapter import OneBotAdapter as A

    events = []
    async def on_event(ev):
        events.append(ev)
    a = A(_cfg(**cfg_kw), on_event=on_event)
    a._conn = _FakeConn()
    return a


@pytest.mark.asyncio
async def test_send_group_msg_success():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="received: hello")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    # adapter must have sent a send_group_msg action with an echo
    assert len(a._conn.sent) == 1
    frame = json.loads(a._conn.sent[0])
    assert frame["action"] == "send_group_msg"
    assert frame["params"]["group_id"] == 123
    assert frame["params"]["message"] == "received: hello"
    assert "echo" in frame
    # respond with matching echo
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0  # pending cleaned up after success


@pytest.mark.asyncio
async def test_send_private_msg_success():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="777", conversation_type=ConversationType.PRIVATE, text="hi")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    frame = json.loads(a._conn.sent[0])
    assert frame["action"] == "send_private_msg"
    assert frame["params"]["user_id"] == 777
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task, 1.0)


@pytest.mark.asyncio
async def test_action_error_retcode_raises():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    frame = json.loads(a._conn.sent[0])
    a._resolve_action_response({"status": "failed", "retcode": 100, "echo": frame["echo"], "msg": "bad"})
    with pytest.raises(ActionFailure):
        await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_timeout_raises_and_cleans_pending():
    a = await _make_adapter(action_timeout_s=0.1)
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    with pytest.raises(ActionFailure, match="timed out"):
        await asyncio.wait_for(a.send(msg), 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_disconnect_fails_all_pending_immediately():
    a = await _make_adapter(action_timeout_s=10.0)  # long timeout, but disconnect should fail fast
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    a._fail_all_pending("connection lost")
    with pytest.raises(ActionFailure, match="connection lost"):
        await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_unknown_echo_safe_ignore():
    a = await _make_adapter()
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": "no-such-echo"})
    # no exception, no crash; pending map still empty
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_duplicate_echo_safe_ignore():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    frame = json.loads(a._conn.sent[0])
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task, 1.0)
    # late duplicate: safe ignore (already done)
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})


@pytest.mark.asyncio
async def test_pending_cleaned_after_success():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    frame = json.loads(a._conn.sent[0])
    assert len(a._pending) == 1
    a._resolve_action_response({"status": "ok", "retcode": 0, "echo": frame["echo"]})
    await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_pending_cleaned_after_timeout():
    a = await _make_adapter(action_timeout_s=0.1)
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    with pytest.raises(ActionFailure):
        await asyncio.wait_for(a.send(msg), 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_pending_cleaned_after_disconnect():
    a = await _make_adapter()
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    send_task = asyncio.create_task(a.send(msg))
    await asyncio.sleep(0.05)
    a._fail_all_pending("connection lost")
    with pytest.raises(ActionFailure):
        await asyncio.wait_for(send_task, 1.0)
    assert len(a._pending) == 0


@pytest.mark.asyncio
async def test_max_pending_bound():
    a = await _make_adapter(max_pending_actions=1)
    # fill the pending map with an unresolved future
    fut = asyncio.get_running_loop().create_future()
    a._pending["stale-echo"] = fut
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    with pytest.raises(ActionFailure, match="limit"):
        await asyncio.wait_for(a.send(msg), 1.0)
    assert len(a._pending) == 1  # not leaked


@pytest.mark.asyncio
async def test_no_connection_raises():
    a = await _make_adapter()
    a._conn = None
    msg = OutgoingMessage(conversation_id="123", conversation_type=ConversationType.GROUP, text="x")
    with pytest.raises(ActionFailure, match="no active connection"):
        await a.send(msg)
