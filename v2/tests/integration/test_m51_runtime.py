"""M5.1 runtime readiness and rollback tests."""

from __future__ import annotations

import socket
from dataclasses import replace

import httpx
import pytest

from campuscue.app.runtime import CampusRuntime
from campuscue.config import ApiConfig, OneBotConfig, RuntimeConfig, TaskPipelineConfig


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _runtime_config(tmp_path, *, api_port: int, onebot_port: int) -> RuntimeConfig:
    return replace(
        RuntimeConfig(),
        onebot=OneBotConfig(port=onebot_port),
        tasks=TaskPipelineConfig(
            enabled=True,
            database_path=str(tmp_path / "runtime.db"),
            database_path_explicit=True,
            timezone="Asia/Shanghai",
        ),
        api=ApiConfig(enabled=True, port=api_port, sse_heartbeat_interval=0.05),
    )


@pytest.mark.asyncio
async def test_runtime_waits_for_api_bind_and_serves_health(tmp_path):
    runtime = CampusRuntime(
        _runtime_config(tmp_path, api_port=_free_port(), onebot_port=_free_port())
    )
    await runtime.start()
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{runtime.config.api.port}") as client:
            response = await client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.json()["runtime"] == "RUNNING"
        assert runtime.state.value == "RUNNING"
    finally:
        await runtime.stop()
    assert runtime.state.value == "STOPPED"


@pytest.mark.asyncio
async def test_runtime_api_bind_failure_rolls_back_all_started_components(tmp_path):
    api_port = _free_port()
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", api_port))
    blocker.listen(1)
    runtime = CampusRuntime(
        _runtime_config(tmp_path, api_port=api_port, onebot_port=_free_port())
    )
    try:
        with pytest.raises(RuntimeError, match="API server failed during startup"):
            await runtime.start()
        assert runtime.state.value == "FAILED"
        assert runtime._api_task is None
        assert runtime._database is None
        assert runtime.adapter is not None
        assert runtime.adapter.status()["listening"] is False
        assert runtime.bus is not None
    finally:
        blocker.close()
