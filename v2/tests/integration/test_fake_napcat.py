"""Integration tests: real CampusCue WS server + fake NapCat client.

Covers the full M1 chain: fake client message -> Adapter -> CampusEvent ->
EventBus -> Router -> EchoHandler -> send action -> fake client responds ->
send Future resolves. Uses ephemeral ports.
"""

from __future__ import annotations

import asyncio
import json
import socket

import pytest
from websockets.asyncio.client import connect

from campuscue.app.runtime import CampusRuntime
from campuscue.config import RuntimeConfig


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _config(**kw):
    base = dict(host="127.0.0.1", port=_free_port(), path="/ws", access_token=None,
                action_timeout_s=2.0, max_pending_actions=16, dedup_ttl_s=300,
                dedup_capacity=1000)
    base.update(kw.pop("onebot", {}))
    from campuscue.config import EventBusConfig, OneBotConfig

    return RuntimeConfig(
        onebot=OneBotConfig(**base),
        event_bus=EventBusConfig(queue_maxsize=64, max_in_flight=16),
        diagnostic=False,
    )


def _group_hello(seq=1, sender=555, group=123, self_id=10001):
    return {
        "post_type": "message",
        "self_id": self_id,
        "message_id": 9000 + seq,
        "message_type": "group",
        "group_id": group,
        "sender": {"user_id": sender, "card": "同学", "nickname": "同学"},
        "time": 1723200000 + seq,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }


class _FakeNapCat:
    """Reverse WS client: connects, sends events, auto-answers actions."""

    def __init__(self, uri, token=None):
        self.uri = uri
        self.token = token
        self.ws = None
        self.received_actions: list[dict] = []

    async def connect(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        self.ws = await connect(self.uri, additional_headers=headers, open_timeout=5)

    async def send_event(self, payload: dict):
        await self.ws.send(json.dumps(payload))

    async def wait_action(self, action: str, timeout: float = 3.0) -> dict:
        """Wait for the next action frame of the given type; auto-answer it."""
        async def loop():
            while True:
                raw = await self.ws.recv()
                data = json.loads(raw)
                if data.get("action") == action:
                    self.received_actions.append(data)
                    # auto-answer success
                    await self.ws.send(json.dumps({
                        "status": "ok", "retcode": 0,
                        "echo": data["echo"], "data": {"message_id": 42},
                    }))
                    return data
        return await asyncio.wait_for(loop(), timeout)

    async def close(self):
        if self.ws is not None:
            await self.ws.close()


@pytest.mark.asyncio
async def test_full_chain_group_hello():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        await nc.send_event(_group_hello())
        action = await nc.wait_action("send_group_msg")
        assert action["params"]["group_id"] == 123
        assert action["params"]["message"] == "received: hello"
        assert action["echo"]
    finally:
        await nc.close()
        await rt.stop()
    assert rt.state.value == "STOPPED"


@pytest.mark.asyncio
async def test_private_hello():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        await nc.send_event({
            "post_type": "message",
            "self_id": 10001,
            "message_id": 7001,
            "message_type": "private",
            "user_id": 555,
            "sender": {"user_id": 555, "nickname": "我"},
            "time": 1723200100,
            "message": [{"type": "text", "data": {"text": "hello"}}],
        })
        action = await nc.wait_action("send_private_msg")
        assert action["params"]["user_id"] == 555
        assert action["params"]["message"] == "received: hello"
    finally:
        await nc.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_duplicate_message_single_action():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        p = _group_hello(seq=1)
        await nc.send_event(p)
        await nc.wait_action("send_group_msg")
        # same self_id + message_id delivered again (reconnect duplicate)
        await nc.send_event(p)
        # give the pipeline time to process the duplicate; it must NOT produce an action
        await asyncio.sleep(0.3)
        assert len(nc.received_actions) == 1
    finally:
        await nc.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_self_message_no_reply():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        # bot's own message: sender_id == self_id == 10001
        await nc.send_event(_group_hello(seq=2, sender=10001))
        await asyncio.sleep(0.3)
        assert len(nc.received_actions) == 0
    finally:
        await nc.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_non_hello_traffic_no_echo():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        # realistic traffic: casual chat, heartbeat meta, notice
        await nc.send_event(_group_hello(seq=3).__class__({
            **{"post_type": "message", "message_id": 6001, "self_id": 10001,
               "message_type": "group", "group_id": 123,
               "sender": {"user_id": 555, "nickname": "x"},
               "time": 1723200200,
               "message": [{"type": "text", "data": {"text": "今晚吃什么"}}]},
        }))
        await nc.send_event({"post_type": "meta_event", "meta_event_type": "heartbeat", "time": 1723200201})
        await nc.send_event({"post_type": "notice", "notice_type": "group_increase", "group_id": 123, "user_id": 777})
        await asyncio.sleep(0.4)
        assert len(nc.received_actions) == 0
    finally:
        await nc.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_second_connection_replaces_first():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc_a = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    nc_b = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc_a.connect()
        await nc_b.connect()  # B replaces A -> server closes A
        await asyncio.sleep(0.2)
        # B works
        await nc_b.send_event(_group_hello(seq=10))
        await nc_b.wait_action("send_group_msg")
        # A is stale: server closed it; sending on A must not produce any action
        try:
            await nc_a.send_event(_group_hello(seq=11))
        except Exception:
            pass  # connection closed by server (stale replacement) - expected
        await asyncio.sleep(0.3)
        assert len(nc_a.received_actions) == 0
        assert len(nc_b.received_actions) == 1
    finally:
        await nc_a.close()
        await nc_b.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_token_rejected_when_configured():
    cfg = _config(onebot={"access_token": "fake-token-123"})
    rt = CampusRuntime(cfg)
    await rt.start()
    uri = f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}"
    # wrong / missing token -> handshake rejected
    nc_bad = _FakeNapCat(uri)
    with pytest.raises(Exception):
        await asyncio.wait_for(nc_bad.connect(), 3.0)
    await nc_bad.close()
    # correct token -> connects fine
    nc_ok = _FakeNapCat(uri, token="fake-token-123")
    await asyncio.wait_for(nc_ok.connect(), 3.0)
    await nc_ok.send_event(_group_hello(seq=20))
    await nc_ok.wait_action("send_group_msg")
    await nc_ok.close()
    await rt.stop()


@pytest.mark.asyncio
async def test_invalid_data_resilience():
    cfg = _config()
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        # garbage frames must not kill the server
        await nc.ws.send("not json at all")
        await nc.ws.send("[1,2,3]")
        await nc.ws.send(json.dumps({"post_type": "message", "message_id": 1}))  # missing fields
        await nc.ws.send(json.dumps({"post_type": "bogus", "echo": 123}))  # bad echo type
        await asyncio.sleep(0.3)
        # a valid hello afterwards still works
        await nc.send_event(_group_hello(seq=30))
        await nc.wait_action("send_group_msg")
    finally:
        await nc.close()
        await rt.stop()


@pytest.mark.asyncio
async def test_disconnect_fails_pending_immediately():
    cfg = _config(onebot={"action_timeout_s": 10.0})
    rt = CampusRuntime(cfg)
    await rt.start()
    nc = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
    try:
        await nc.connect()
        await nc.send_event(_group_hello(seq=40))
        # wait until the action is sent but NOT answered (auto-answer disabled)
        raw = await asyncio.wait_for(nc.ws.recv(), 3.0)
        data = json.loads(raw)
        assert data["action"] == "send_group_msg"
        # close connection while pending -> pending must fail fast, no crash
        await nc.close()
        await asyncio.sleep(0.3)
        # runtime still healthy: reconnect works
        nc2 = _FakeNapCat(f"ws://127.0.0.1:{cfg.onebot.port}{cfg.onebot.path}")
        await nc2.connect()
        await nc2.send_event(_group_hello(seq=41))
        await nc2.wait_action("send_group_msg")
        await nc2.close()
    finally:
        await rt.stop()
