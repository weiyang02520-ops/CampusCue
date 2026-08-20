"""M5 RealtimeHub/SSE tests."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from campuscue.api.dependencies import APIDependencies
from campuscue.api.realtime import RealtimeHub
from campuscue.api.app import create_app
from campuscue.config import ApiConfig
from campuscue.storage.database import Database, DatabaseConfig


def test_hub_publishes_and_disconnects_slow_subscriber():
    hub = RealtimeHub(queue_size=2)
    sub_id, queue = hub.subscribe()

    async def run():
        await hub.publish("task.created", {"id": 1})
        ev = await asyncio.wait_for(queue.get(), timeout=1)
        assert ev.event == "task.created"
        assert ev.data["id"] == 1
        # slow subscriber: fill queue without consuming, next publish drops it
        await hub.publish("task.updated", {"id": 2})
        await hub.publish("task.updated", {"id": 3})
        await hub.publish("task.updated", {"id": 4})
        assert hub.subscriber_count() == 0

    asyncio.run(run())


def test_slow_stream_terminates_after_queue_overflow():
    hub = RealtimeHub(queue_size=2)
    sub_id, queue = hub.subscribe()

    async def run():
        stream = hub.stream(sub_id, queue, heartbeat_interval_s=1)
        await hub.publish("task.updated", {"id": 1})
        await hub.publish("task.updated", {"id": 2})
        first = await anext(stream)
        assert '"id": 1' in first
        # The generator is paused after yielding; fill its remaining slot and
        # overflow it. The close event must wake the next anext() call.
        await hub.publish("task.updated", {"id": 3})
        await hub.publish("task.updated", {"id": 4})
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), timeout=1)
        assert hub.subscriber_count() == 0

    asyncio.run(run())


def test_stream_cleanup_on_consumer_disconnect():
    hub = RealtimeHub(queue_size=2)
    sub_id, queue = hub.subscribe()

    async def run():
        stream = hub.stream(sub_id, queue, heartbeat_interval_s=1)
        next_chunk = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        assert hub.subscriber_count() == 1
        with contextlib.suppress(asyncio.CancelledError):
            next_chunk.cancel()
            await next_chunk
        assert hub.subscriber_count() == 0

    asyncio.run(run())


def test_slow_subscriber_does_not_block_or_disconnect_normal_subscriber():
    hub = RealtimeHub(queue_size=1)
    slow_id, slow_queue = hub.subscribe()
    normal_id, normal_queue = hub.subscribe()

    async def run():
        await hub.publish("task.created", {"id": 1})
        assert (await normal_queue.get()).data["id"] == 1
        await hub.publish("task.updated", {"id": 2})
        assert (await normal_queue.get()).data["id"] == 2
        await hub.publish("task.updated", {"id": 3})
        assert hub.subscriber_count() == 1
        assert normal_id in hub._subscribers
        assert slow_id not in hub._subscribers
        assert (await normal_queue.get()).data["id"] == 3

    asyncio.run(run())


def test_sse_route_registered(tmp_path: Path):
    db = Database(DatabaseConfig(path=tmp_path / "sse.db", env="test"))
    asyncio.run(db.initialize())
    deps = APIDependencies(config=ApiConfig(enabled=True), database=db)
    client = TestClient(create_app(deps))
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/stream" in paths
    assert "/api/v1/health" in paths
    assert "/api/v1/system/health" not in paths
    asyncio.run(db.dispose())


def test_sse_route_uses_configured_heartbeat(tmp_path: Path):
    db = Database(DatabaseConfig(path=tmp_path / "sse-heartbeat.db", env="test"))
    asyncio.run(db.initialize())
    deps = APIDependencies(
        config=ApiConfig(enabled=True, sse_heartbeat_interval=0.01),
        database=db,
    )
    captured = {}

    async def finite_stream(sub_id, queue, *, heartbeat_interval_s):
        captured["heartbeat_interval_s"] = heartbeat_interval_s
        try:
            yield ": ping\n\n"
        finally:
            deps.realtime.unsubscribe(sub_id)

    deps.realtime.stream = finite_stream
    client = TestClient(create_app(deps))
    response = client.get("/api/v1/stream")
    assert response.status_code == 200
    assert captured["heartbeat_interval_s"] == 0.01
    assert deps.realtime.subscriber_count() == 0
    asyncio.run(db.dispose())
