"""M7.3 bounded Agent confirmation and trace contract tests."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.core.events import ConversationType
from campuscue.providers.models import LLMResponse, LLMToolCall
from campuscue.storage.clock import FixedClock
from campuscue.tools.registry import ToolRegistry
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 20, 4, 0, tzinfo=timezone.utc)


class ScriptProvider:
    model = "m73-deterministic"
    max_context_tokens = 4096

    def __init__(self, *responses: LLMResponse):
        self.responses = list(responses)
        self.requests = []

    async def chat(self, request):
        self.requests.append(request)
        return self.responses[min(len(self.requests) - 1, len(self.responses) - 1)]


@pytest.fixture
async def env(tmp_path):
    from campuscue.repositories.repositories import ReminderRepository, SourceRepository, TaskRepository
    from campuscue.services.reminder_service import NoopScheduler, ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.reminder_policy import ReminderPolicy

    db = Database(DatabaseConfig(path=tmp_path / "m73.db", env="test"))
    await db.initialize()
    clock = FixedClock(NOW)
    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)
    reminder_service = ReminderService(
        reminders,
        tasks,
        scheduler=NoopScheduler(),
        clock=clock,
        timezone=TZ,
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)
    source_a = await sources.create(platform="onebot", conversation_id="m73-a", name="A")
    source_b = await sources.create(platform="onebot", conversation_id="m73-b", name="B")
    yield {
        "db": db,
        "clock": clock,
        "sources": sources,
        "tasks": tasks,
        "task_service": task_service,
        "reminder_service": reminder_service,
        "source_a": source_a,
        "source_b": source_b,
    }
    await db.dispose()


def _ctx(source_id: int, *, conversation_id: str = "shared-thread", message_id: str = "m73"):
    return AgentContext(
        platform="onebot",
        source_id=source_id,
        conversation_id=conversation_id,
        conversation_type=ConversationType.GROUP,
        message_id=message_id,
        timestamp=NOW,
        trace_id=f"trace-{message_id}",
        timezone=TZ,
        user_text="用户请求",
    )


def _runtime(env, provider):
    registry = ToolRegistry()
    register_task_tools(
        registry,
        task_service=env["task_service"],
        reminder_service=env["reminder_service"],
        tz=TZ,
        clock=env["clock"],
    )
    return CampusAgentRuntime(
        tools=registry,
        provider=provider,
        timezone=TZ,
        clock=env["clock"],
        max_context_tokens=4096,
    )


def _tool(name: str, arguments: dict):
    return LLMResponse(
        role="assistant",
        content="",
        usage={},
        raw={},
        tool_calls=(LLMToolCall("m73-call", name, arguments),),
    )


@pytest.mark.asyncio
async def test_m73_mutation_requires_confirmation_then_executes_once(env):
    task = await env["task_service"].create_manual_task(
        title="高等数学第三章作业", course="高等数学", source_id=env["source_a"].id,
    )
    provider = ScriptProvider(_tool("task_update", {"task_id": task.id, "title": "高数第三章作业（更新）"}))
    runtime = _runtime(env, provider)

    proposal = await runtime.chat_with_trace(
        context=_ctx(env["source_a"].id), user_text="把高数作业标题改一下"
    )
    unchanged = await env["tasks"].get(task.id)
    assert unchanged.title == "高等数学第三章作业"
    assert proposal.confirmation_state == "pending"
    assert "确认" in proposal.message
    assert any("等待确认" in item for item in proposal.tool_activity)
    assert provider.requests and len(provider.requests) == 1

    confirmed = await runtime.chat_with_trace(
        context=_ctx(env["source_a"].id, message_id="m73-confirm"), user_text="确认"
    )
    changed = await env["tasks"].get(task.id)
    assert changed.title == "高数第三章作业（更新）"
    assert confirmed.confirmation_state == "confirmed"

    replay = await runtime.chat_with_trace(
        context=_ctx(env["source_a"].id, message_id="m73-replay"), user_text="确认"
    )
    assert replay.confirmation_state != "confirmed"
    assert changed.title == (await env["tasks"].get(task.id)).title


@pytest.mark.asyncio
async def test_m73_reject_and_ambiguous_confirmation_do_not_mutate(env):
    task = await env["task_service"].create_manual_task(title="原任务", source_id=env["source_a"].id)
    provider = ScriptProvider(_tool("task_update", {"task_id": task.id, "title": "新任务"}))
    runtime = _runtime(env, provider)
    await runtime.chat_with_trace(context=_ctx(env["source_a"].id), user_text="改标题")
    ambiguous = await runtime.chat_with_trace(context=_ctx(env["source_a"].id, message_id="m73-amb"), user_text="嗯")
    assert "明确回复" in ambiguous.message
    assert (await env["tasks"].get(task.id)).title == "原任务"
    rejected = await runtime.chat_with_trace(context=_ctx(env["source_a"].id, message_id="m73-no"), user_text="取消")
    assert rejected.confirmation_state == "cancelled"
    assert (await env["tasks"].get(task.id)).title == "原任务"


@pytest.mark.asyncio
async def test_m73_cross_source_confirmation_is_rejected(env):
    task = await env["task_service"].create_manual_task(title="A任务", source_id=env["source_a"].id)
    provider = ScriptProvider(_tool("task_update", {"task_id": task.id, "title": "不应修改"}))
    runtime = _runtime(env, provider)
    await runtime.chat_with_trace(context=_ctx(env["source_a"].id), user_text="改标题")
    result = await runtime.chat_with_trace(context=_ctx(env["source_b"].id, message_id="m73-cross"), user_text="确认")
    assert result.confirmation_state == "cancelled"
    assert "来源" in result.message
    assert (await env["tasks"].get(task.id)).title == "A任务"


@pytest.mark.asyncio
async def test_m73_read_activity_is_real_and_private(env):
    task = await env["task_service"].create_manual_task(title="可见任务", source_id=env["source_a"].id)
    provider = ScriptProvider(
        _tool("task_list", {"scope": "open"}),
        LLMResponse(role="assistant", content="你有一个待办。", usage={}, raw={}),
    )
    runtime = _runtime(env, provider)
    result = await runtime.chat_with_trace(context=_ctx(env["source_a"].id), user_text="查一下任务")
    assert result.message == "你有一个待办。"
    assert "已查询当前来源的任务" in result.tool_activity
    assert all("task_list" not in item for item in result.tool_activity)
    assert all("source_id" not in item for item in result.tool_activity)
    assert task.id > 0


@pytest.mark.asyncio
async def test_m73_restart_clears_pending_approval(env):
    task = await env["task_service"].create_manual_task(title="原任务", source_id=env["source_a"].id)
    runtime = _runtime(env, ScriptProvider(_tool("task_update", {"task_id": task.id, "title": "不执行"})))
    await runtime.chat_with_trace(context=_ctx(env["source_a"].id), user_text="改标题")
    restarted = _runtime(env, ScriptProvider(LLMResponse(role="assistant", content="收到。", usage={}, raw={})))
    result = await restarted.chat_with_trace(context=_ctx(env["source_a"].id), user_text="确认")
    assert result.message == "收到。"
    assert (await env["tasks"].get(task.id)).title == "原任务"
