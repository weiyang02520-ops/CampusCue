"""M5 RealtimeHub/SSE tests."""

from __future__ import annotations

import asyncio
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


def test_sse_route_registered(tmp_path: Path):
    db = Database(DatabaseConfig(path=tmp_path / "sse.db", env="test"))
    asyncio.run(db.initialize())
    deps = APIDependencies(config=ApiConfig(enabled=True), database=db)
    client = TestClient(create_app(deps))
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/stream" in paths
    asyncio.run(db.dispose())
