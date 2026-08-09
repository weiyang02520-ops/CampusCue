"""M1.1 regression tests: finding D (config bounds), E (WS path), F (strict
response validation), H (raw_message removed), B (outbound inside handler bound)."""

from __future__ import annotations

import asyncio
import json

import pytest

from campuscue.adapters.onebot.protocol import is_success
from campuscue.config import EventBusConfig, OneBotConfig, RuntimeConfig


# ---------------------------------------------------------------- D: config

class TestConfigValidation:
    def _cfg(self, **kw):
        base = dict(host="127.0.0.1", port=6199, path="/ws", access_token=None,
                    action_timeout_s=10.0, max_pending_actions=4, dedup_ttl_s=300,
                    dedup_capacity=100)
        base.update(kw)
        return base

    def test_queue_maxsize_zero_rejected(self):
        with pytest.raises(ValueError, match="queue_maxsize"):
            RuntimeConfig(event_bus=EventBusConfig(queue_maxsize=0, max_in_flight=4))

    def test_max_in_flight_zero_rejected(self):
        with pytest.raises(ValueError, match="max_in_flight"):
            RuntimeConfig(event_bus=EventBusConfig(queue_maxsize=10, max_in_flight=0))

    def test_max_pending_zero_rejected(self):
        with pytest.raises(ValueError, match="max_pending_actions"):
            RuntimeConfig(onebot=OneBotConfig(**self._cfg(max_pending_actions=0)))

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValueError, match="action_timeout_s"):
            RuntimeConfig(onebot=OneBotConfig(**self._cfg(action_timeout_s=-1.0)))

    def test_zero_dedup_capacity_rejected(self):
        with pytest.raises(ValueError, match="dedup_capacity"):
            RuntimeConfig(onebot=OneBotConfig(**self._cfg(dedup_capacity=0)))

    def test_invalid_port_rejected(self):
        with pytest.raises(ValueError, match="port"):
            RuntimeConfig(onebot=OneBotConfig(**self._cfg(port=70000)))

    def test_invalid_path_rejected(self):
        with pytest.raises(ValueError, match="path"):
            RuntimeConfig(onebot=OneBotConfig(**self._cfg(path="ws")))

    def test_valid_config_accepted(self):
        RuntimeConfig()  # defaults must be valid


# ---------------------------------------------------------------- F: strict response

class TestStrictResponseValidation:
    def test_full_success_passes(self):
        assert is_success({"status": "ok", "retcode": 0}) is True

    def test_missing_status_fails(self):
        assert is_success({"retcode": 0}) is False

    def test_missing_retcode_fails(self):
        assert is_success({"status": "ok"}) is False

    def test_missing_both_fails(self):
        assert is_success({}) is False

    def test_status_failed_fails(self):
        assert is_success({"status": "failed", "retcode": 0}) is False

    def test_retcode_nonzero_fails(self):
        assert is_success({"status": "ok", "retcode": 1}) is False

    def test_none_values_fail(self):
        assert is_success({"status": None, "retcode": None}) is False


# ---------------------------------------------------------------- H: raw_message removed

class TestNoRawMessageInDomain:
    def test_converter_has_no_raw_message_metadata(self):
        from campuscue.adapters.onebot.converter import convert_message

        ev = convert_message({
            "post_type": "message", "self_id": 10001, "message_id": 1,
            "message_type": "group", "group_id": 123,
            "sender": {"user_id": 5, "nickname": "x"},
            "time": 1723200000,
            "message": [{"type": "text", "data": {"text": "hello"}}],
            "raw_message": "hello raw",  # OneBot dialect must NOT leak
        }, adapter_id="t")
        assert "raw_message" not in ev.metadata
        assert ev.text == "hello"


# ---------------------------------------------------------------- E: WS path (integration)

@pytest.mark.asyncio
async def test_wrong_path_rejected_correct_path_accepted():
    from websockets.asyncio.client import connect

    from campuscue.app.runtime import CampusRuntime
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    rt = CampusRuntime(RuntimeConfig(onebot=OneBotConfig(
        host="127.0.0.1", port=port, path="/ws", access_token=None,
        action_timeout_s=2.0, max_pending_actions=4, dedup_ttl_s=300, dedup_capacity=100)))
    await rt.start()
    try:
        # wrong path -> handshake rejected
        with pytest.raises(Exception):
            await asyncio.wait_for(
                connect(f"ws://127.0.0.1:{port}/other", open_timeout=3), 4.0
            )
        # correct path -> connects
        ws = await asyncio.wait_for(
            connect(f"ws://127.0.0.1:{port}/ws", open_timeout=3), 4.0
        )
        await ws.send(json.dumps({
            "post_type": "message", "self_id": 10001, "message_id": 99,
            "message_type": "group", "group_id": 123,
            "sender": {"user_id": 5, "nickname": "x"},
            "time": 1723200000,
            "message": [{"type": "text", "data": {"text": "hello"}}],
        }))
        # expect the echo reply action
        raw = await asyncio.wait_for(ws.recv(), 3.0)
        data = json.loads(raw)
        assert data["action"] == "send_group_msg"
        await ws.send(json.dumps({"status": "ok", "retcode": 0, "echo": data["echo"]}))
        await ws.close()
    finally:
        await rt.stop()


# ---------------------------------------------------------------- B: outbound inside handler bound

@pytest.mark.asyncio
async def test_event_pipeline_concurrency_includes_outbound():
    """max_in_flight bounds the full event->route->outbound pipeline: a slow
    send keeps the handler slot occupied."""
    from campuscue.app.runtime import CampusRuntime
    from campuscue.adapters.onebot.adapter import OneBotAdapter
    from campuscue.core.events import CampusEvent, ConversationType, EventType
    from campuscue.core.outbound import OutgoingMessage
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    busy = asyncio.Event()
    release = asyncio.Event()
    active_sends = 0
    peak_sends = 0

    class SlowAdapter(OneBotAdapter):
        async def send(self, message: OutgoingMessage) -> None:
            nonlocal active_sends, peak_sends
            active_sends += 1
            peak_sends = max(peak_sends, active_sends)
            try:
                await asyncio.wait_for(release.wait(), 2.0)
            finally:
                active_sends -= 1

    rt = CampusRuntime(RuntimeConfig(
        onebot=OneBotConfig(host="127.0.0.1", port=port, path="/ws", access_token=None,
                            action_timeout_s=2.0, max_pending_actions=4,
                            dedup_ttl_s=300, dedup_capacity=100),
        event_bus=EventBusConfig(queue_maxsize=64, max_in_flight=2)))
    rt.adapter = SlowAdapter(rt.config.onebot, on_event=rt.bus.publish if rt.bus else None)
    rt.adapter._conn = "fake-conn"  # only used by real send; SlowAdapter overrides send
    rt.state = "RUNNING"

    # route events directly through the runtime's bus handler
    def ev(i):
        return CampusEvent(
            event_id=f"e{i}", trace_id=f"t{i}", platform="onebot", adapter_id="t",
            event_type=EventType.GROUP_MESSAGE, self_id="10001", message_id=str(i),
            conversation_id="123", conversation_type=ConversationType.GROUP,
            sender_id="5", sender_name="", text="hello",
            timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))

    # run the runtime's handler path with a real bus
    rt.bus = __import__("campuscue.core.bus", fromlist=["EventBus"]).EventBus(
        queue_maxsize=64, max_in_flight=2)
    rt.bus.subscribe(rt._route_event)
    rt.bus.start()
    rt.adapter.on_event = rt.bus.publish  # type: ignore[attr-defined]

    # send 4 events; only 2 pipelines (route+send) may be active at once
    for i in range(4):
        await rt.bus.publish(ev(i))
    await asyncio.sleep(0.3)
    assert peak_sends <= 2
    release.set()
    await rt.bus.shutdown(timeout_s=2.0)
