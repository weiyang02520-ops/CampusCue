"""POST-M7 P1A runtime, Agent, and controlled-process fault tests.

These tests use only loopback WebSockets, disposable SQLite files, and fake
providers/clients.  They prove recovery boundaries without claiming a real QQ
or real provider integration.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from websockets.asyncio.client import connect

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.app.runtime import CampusRuntime
from campuscue.config import EventBusConfig, OneBotConfig, RuntimeConfig
from campuscue.core.events import ConversationType
from campuscue.providers.models import LLMResponse, LLMToolCall
from campuscue.storage.clock import FixedClock
from campuscue.tools.registry import ToolRegistry
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _runtime_config(*, port: int, action_timeout_s: float = 2.0) -> RuntimeConfig:
    return RuntimeConfig(
        onebot=OneBotConfig(
            host="127.0.0.1",
            port=port,
            path="/ws",
            action_timeout_s=action_timeout_s,
            max_pending_actions=16,
            dedup_ttl_s=300,
            dedup_capacity=1000,
        ),
        event_bus=EventBusConfig(queue_maxsize=64, max_in_flight=16),
        diagnostic=False,
    )


def _group_event(seq: int) -> dict:
    return {
        "post_type": "message",
        "self_id": 10001,
        "message_id": 9000 + seq,
        "message_type": "group",
        "group_id": 123,
        "sender": {"user_id": 555, "nickname": "同学"},
        "time": 1723200000 + seq,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }


class _FakeNapCat:
    def __init__(self, uri: str):
        self.ws = None
        self.uri = uri

    async def connect(self):
        self.ws = await connect(self.uri, open_timeout=5)

    async def send_event(self, payload: dict):
        await self.ws.send(json.dumps(payload))

    async def recv_action(self) -> dict:
        while True:
            data = json.loads(await self.ws.recv())
            if data.get("action"):
                return data

    async def answer(self, action: dict):
        await self.ws.send(json.dumps({
            "status": "ok", "retcode": 0, "echo": action["echo"],
            "data": {"message_id": 42},
        }))

    async def close(self):
        if self.ws is not None:
            await self.ws.close()


@pytest.mark.asyncio
async def test_stability_r_a05_reconnect_old_echo_cannot_resolve_new_action():
    """A replaced connection's delayed echo stays in its old generation."""
    runtime = CampusRuntime(_runtime_config(port=_free_port(), action_timeout_s=3))
    await runtime.start()
    uri = f"ws://127.0.0.1:{runtime.config.onebot.port}/ws"
    first = _FakeNapCat(uri)
    second = _FakeNapCat(uri)
    try:
        await first.connect()
        await first.send_event(_group_event(1))
        old_action = await asyncio.wait_for(first.recv_action(), 3)
        await second.connect()
        await asyncio.sleep(0.1)
        await second.send_event(_group_event(2))
        new_action = await asyncio.wait_for(second.recv_action(), 3)

        # An old echo arriving on the new socket is unknown and must not
        # complete the new pending future.
        await second.ws.send(json.dumps({
            "status": "ok", "retcode": 0, "echo": old_action["echo"],
            "data": {"message_id": 41},
        }))
        await asyncio.sleep(0.1)
        assert runtime.adapter.status()["pending_actions"] == 1
        await second.answer(new_action)
        await asyncio.sleep(0.1)
        assert runtime.adapter.status()["pending_actions"] == 0
    finally:
        await first.close()
        await second.close()
        await runtime.stop()


@pytest.mark.asyncio
async def test_stability_r_a08_graceful_stop_closes_active_action_bounded():
    runtime = CampusRuntime(_runtime_config(port=_free_port(), action_timeout_s=30))
    await runtime.start()
    client = _FakeNapCat(f"ws://127.0.0.1:{runtime.config.onebot.port}/ws")
    try:
        await client.connect()
        await client.send_event(_group_event(3))
        await asyncio.wait_for(client.recv_action(), 3)
        started = time.monotonic()
        await runtime.stop()
        assert time.monotonic() - started < 3
        assert runtime.state.value == "STOPPED"
        assert runtime.adapter.status()["pending_actions"] == 0
    finally:
        await client.close()
        await runtime.stop()


class _ScriptProvider:
    model = "p1a-deterministic"
    max_context_tokens = 4096

    def __init__(self, *responses: LLMResponse):
        self.responses = list(responses)
        self.requests = []

    async def chat(self, request):
        self.requests.append(request)
        return self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]


def _ctx(source_id: int, *, message_id: str, thread: str = "p1a-thread") -> AgentContext:
    return AgentContext(
        platform="onebot",
        source_id=source_id,
        conversation_id=thread,
        conversation_type=ConversationType.GROUP,
        message_id=message_id,
        timestamp=NOW,
        trace_id=f"trace-{message_id}",
        timezone=TZ,
        user_text="用户请求",
    )


def _tool(name: str, arguments: dict) -> LLMResponse:
    return LLMResponse(
        role="assistant", content="", usage={}, raw={},
        tool_calls=(LLMToolCall("p1a-call", name, arguments),),
    )


@pytest.fixture
async def agent_env(tmp_path):
    from campuscue.repositories.repositories import ReminderRepository, SourceRepository, TaskRepository
    from campuscue.services.reminder_service import NoopScheduler, ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.reminder_policy import ReminderPolicy

    db = Database(DatabaseConfig(path=tmp_path / "agent.db", env="test"))
    await db.initialize()
    clock = FixedClock(NOW)
    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)
    reminder_service = ReminderService(
        reminders, tasks, scheduler=NoopScheduler(), clock=clock, timezone=TZ,
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)
    source = await sources.create(platform="onebot", conversation_id="p1a", name="P1A")
    yield {"db": db, "source": source, "tasks": tasks, "task_service": task_service, "clock": clock, "reminders": reminders, "reminder_service": reminder_service}
    await db.dispose()


def _agent_runtime(env, provider):
    registry = ToolRegistry()
    register_task_tools(
        registry, task_service=env["task_service"], reminder_service=env["reminder_service"],
        tz=TZ, clock=env["clock"],
    )
    return CampusAgentRuntime(tools=registry, provider=provider, timezone=TZ, clock=env["clock"], max_context_tokens=4096)


@pytest.mark.asyncio
async def test_stability_r_a11_concurrent_confirmation_consumes_proposal_once(agent_env):
    task = await agent_env["task_service"].create_manual_task(
        title="原任务", source_id=agent_env["source"].id,
    )
    provider = _ScriptProvider(
        _tool("task_update", {"task_id": task.id, "title": "只更新一次"}),
        LLMResponse(role="assistant", content="第二个请求没有待执行操作。", usage={}, raw={}),
    )
    runtime = _agent_runtime(agent_env, provider)
    proposal = await runtime.chat_with_trace(
        context=_ctx(agent_env["source"].id, message_id="proposal"), user_text="改标题",
    )
    assert proposal.confirmation_state == "pending"
    first, second = await asyncio.gather(
        runtime.chat_with_trace(context=_ctx(agent_env["source"].id, message_id="confirm-a"), user_text="确认"),
        runtime.chat_with_trace(context=_ctx(agent_env["source"].id, message_id="confirm-b"), user_text="确认"),
    )
    assert sorted(result.confirmation_state or "none" for result in (first, second)) == ["confirmed", "none"]
    assert (await agent_env["tasks"].get(task.id)).title == "只更新一次"
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_stability_r_a12_same_thread_turns_are_serialized(agent_env):
    entered = asyncio.Event()
    release = asyncio.Event()

    class BlockingProvider(_ScriptProvider):
        async def chat(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                entered.set()
                await release.wait()
            return LLMResponse(role="assistant", content=f"回答{len(self.requests)}", usage={}, raw={})

    provider = BlockingProvider()
    runtime = _agent_runtime(agent_env, provider)
    first_task = asyncio.create_task(runtime.chat_with_trace(
        context=_ctx(agent_env["source"].id, message_id="turn-a"), user_text="第一问",
    ))
    await asyncio.wait_for(entered.wait(), 2)
    second_task = asyncio.create_task(runtime.chat_with_trace(
        context=_ctx(agent_env["source"].id, message_id="turn-b"), user_text="第二问",
    ))
    await asyncio.sleep(0.05)
    assert not second_task.done()
    release.set()
    first, second = await asyncio.gather(first_task, second_task)
    assert first.message == "回答1"
    assert second.message == "回答2"
    assert [message.content for message in runtime.conversations[_ctx(agent_env["source"].id, message_id="x").thread].snapshot() if message.role == "user"] == ["第一问", "第二问"]


@pytest.mark.asyncio
async def test_stability_r_a13_cross_source_concurrent_request_fails_closed(agent_env):
    entered = asyncio.Event()
    release = asyncio.Event()

    class BlockingProvider(_ScriptProvider):
        async def chat(self, request):
            self.requests.append(request)
            entered.set()
            await release.wait()
            return LLMResponse(role="assistant", content="A 的回答", usage={}, raw={})

    provider = BlockingProvider()
    runtime = _agent_runtime(agent_env, provider)
    # Use a distinct source id with the same thread; source binding is checked
    # before the second request can read history or call the provider.
    source_b_id = agent_env["source"].id + 999
    first_task = asyncio.create_task(runtime.chat_with_trace(
        context=_ctx(agent_env["source"].id, message_id="source-a"), user_text="A",
    ))
    await asyncio.wait_for(entered.wait(), 2)
    blocked = await runtime.chat_with_trace(
        context=_ctx(source_b_id, message_id="source-b"), user_text="B",
    )
    assert "开启新对话" in blocked.message
    assert blocked.tool_activity == ["已阻止跨来源对话复用"]
    assert len(provider.requests) == 1
    release.set()
    assert (await first_task).message == "A 的回答"


@pytest.mark.parametrize("termination", ["terminate", "kill"])
def test_stability_r_a10_controlled_worker_stop_reopens_and_resyncs(tmp_path, termination):
    db_path = tmp_path / f"worker-{termination}.db"
    marker = tmp_path / f"worker-{termination}.ready"
    repo_root = Path(__file__).resolve().parents[2]
    source_root = repo_root / "src"
    child = f"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from campuscue.repositories.repositories import TaskRepository
from campuscue.storage.database import Database, DatabaseConfig
from campuscue.storage.clock import SystemClock

async def main():
    db = Database(DatabaseConfig(path={str(db_path)!r}, env='test'))
    await db.initialize()
    tasks = TaskRepository(db.session, clock=SystemClock())
    await tasks.create(title='controlled recovery task', deadline=datetime(2026, 9, 1, tzinfo=timezone.utc))
    Path({str(marker)!r}).write_text('ready', encoding='utf-8')
    await asyncio.Event().wait()

asyncio.run(main())
"""
    child_env = os.environ.copy()
    child_env["PYTHONPATH"] = str(source_root)
    proc = subprocess.Popen([sys.executable, "-c", child], cwd=repo_root, env=child_env)
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert marker.exists(), "controlled CampusCue worker did not reach ready state"
        if termination == "terminate":
            proc.terminate()
        else:
            proc.kill()
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    async def reopen():
        from campuscue.repositories.repositories import ReminderRepository, TaskRepository
        from campuscue.services.reminder_service import NoopScheduler, ReminderService
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.tasks.reminder_policy import ReminderPolicy

        db = Database(DatabaseConfig(path=db_path, env="test"))
        await db.initialize()
        clock = FixedClock(datetime(2026, 8, 22, tzinfo=timezone.utc))
        tasks = TaskRepository(db.session, clock=clock)
        reminders = ReminderRepository(db.session, clock=clock)
        scheduler = NoopScheduler()
        service = ReminderService(
            reminders, tasks, scheduler=scheduler, clock=clock, timezone=TZ,
            policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
        )
        rows = await tasks.list_all()
        installed = await service.resync_all()
        await db.dispose()
        return rows, installed

    rows, installed = asyncio.run(reopen())
    assert [row.title for row in rows] == ["controlled recovery task"]
    assert installed >= 0
