"""M7.1 first-use activation contract tests.

These tests use the real extraction pipeline, repositories, TaskService, and
Agent tools with deterministic provider doubles. They do not represent a
production connector or QQ reminder delivery.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.core.events import CampusEvent, ConversationType, EventType
from campuscue.providers.models import LLMResponse, LLMToolCall
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.storage.clock import FixedClock
from campuscue.storage.enums import ExtractionStatus
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import ToolRegistry
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
OFFICIAL_FIXTURE = "高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。"
UNCERTAIN_FIXTURE = "高等数学第三章作业记得尽快交。"


def _event(*, conversation: str, message_id: str, text: str) -> CampusEvent:
    return CampusEvent(
        event_id=f"event-{message_id}",
        trace_id=f"trace-{message_id}",
        platform="onebot",
        adapter_id="m71-test-adapter",
        event_type=EventType.GROUP_MESSAGE,
        self_id="10001",
        message_id=message_id,
        conversation_id=conversation,
        conversation_type=ConversationType.GROUP,
        sender_id="student-1",
        sender_name="",
        text=text,
        timestamp=NOW,
    )


def _provider_for_fixture() -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        text = body["messages"][-1]["content"]
        if OFFICIAL_FIXTURE in text:
            result = {
                "has_task": True,
                "category": "homework",
                "title": "高等数学第三章作业",
                "course": "高等数学",
                "deadline_phrase": "2026年8月28日22:00前",
                "confidence": 0.96,
                "reason": "明确课程、事项与截止时间",
            }
        else:
            result = {
                "has_task": True,
                "category": "homework",
                "title": "高等数学第三章作业",
                "course": "高等数学",
                "deadline_phrase": None,
                "confidence": 0.55,
                "reason": "缺少明确截止时间，需要确认",
            }
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}}], "usage": {}},
        )

    return OpenAICompatibleProvider(
        base_url="https://m71.test/v1",
        model="m71-deterministic",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
async def env(tmp_path):
    from campuscue.providers.manager import ProviderManager
    from campuscue.repositories.repositories import ExtractionRepository, ProviderConfigRepository, ReminderRepository, SourceRepository, TaskRepository
    from campuscue.services.reminder_service import NoopScheduler, ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.pipeline import TaskPipeline
    from campuscue.tasks.reminder_policy import ReminderPolicy

    db = Database(DatabaseConfig(path=tmp_path / "m71.db", env="test"))
    await db.initialize()
    clock = FixedClock(NOW)
    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    extractions = ExtractionRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)
    configs = ProviderConfigRepository(db.session, clock=clock)
    reminder_service = ReminderService(
        reminders,
        tasks,
        scheduler=NoopScheduler(),
        clock=clock,
        timezone=TZ,
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)
    pipeline = TaskPipeline(
        sources=sources,
        extractions=extractions,
        task_service=task_service,
        provider_manager=ProviderManager(configs),
        timezone=TZ,
        clock=clock,
    )
    pipeline._provider_manager = _Manager(_provider_for_fixture())
    yield {
        "db": db,
        "sources": sources,
        "tasks": tasks,
        "extractions": extractions,
        "task_service": task_service,
        "reminders": reminders,
        "reminder_service": reminder_service,
        "pipeline": pipeline,
    }
    await db.dispose()


class _Manager:
    def __init__(self, provider):
        self.provider = provider

    async def get_default(self):
        return self.provider


@pytest.mark.asyncio
async def test_m7_a01_first_source_connection(env):
    source = await env["sources"].create(platform="onebot", conversation_id="m71-campus", name="M7.1 学习群")
    assert source.platform == "onebot"
    assert source.conversation_id == "m71-campus"
    assert source.enabled is True
    assert await env["sources"].get_by_identity("onebot", "m71-campus")


@pytest.mark.asyncio
async def test_m7_a02_connection_failure_disabled_source_is_safe(env):
    source = await env["sources"].create(platform="onebot", conversation_id="m71-disabled", enabled=False)
    await env["pipeline"].handle(_event(conversation="m71-disabled", message_id="m71-fail", text=OFFICIAL_FIXTURE))
    assert await env["tasks"].list_all() == []
    assert await env["extractions"].list_for_message("m71-fail") == []
    assert source.enabled is False


@pytest.mark.asyncio
async def test_m7_a03_official_fixture_runs_extraction_to_canonical_task(env):
    await env["sources"].create(platform="onebot", conversation_id="m71-official", name="高数课程群")
    await env["pipeline"].handle(_event(conversation="m71-official", message_id="m71-official", text=OFFICIAL_FIXTURE))
    tasks = await env["tasks"].list_all()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.title == "高等数学第三章作业"
    assert task.category == "homework"
    assert task.course == "高等数学"
    assert task.deadline == datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
    assert task.source_message_id == "m71-official"
    assert task.source_text_reference == OFFICIAL_FIXTURE
    assert task.status == "pending"
    rows = await env["extractions"].list_for_message("m71-official")
    assert len(rows) == 1 and rows[0].status == ExtractionStatus.SUCCESS.value
    audit = json.loads(rows[0].audit)
    assert audit["outcome"]["task_id"] == task.id
    assert audit["l3"]["confidence"] == 0.96


@pytest.mark.asyncio
async def test_m7_a04_uncertain_fixture_keeps_deadline_unknown_and_needs_review(env):
    await env["sources"].create(platform="onebot", conversation_id="m71-uncertain")
    await env["pipeline"].handle(_event(conversation="m71-uncertain", message_id="m71-uncertain", text=UNCERTAIN_FIXTURE))
    task = (await env["tasks"].list_all())[0]
    assert task.deadline is None
    assert task.status == "pending_confirm"
    assert task.confidence == 0.55
    assert "确认" in (task.description or "")


@pytest.mark.asyncio
async def test_m7_a05_provenance_facts_are_available_without_raw_audit_dump(env):
    source = await env["sources"].create(platform="onebot", conversation_id="m71-provenance", name="高数课程群")
    await env["pipeline"].handle(_event(conversation="m71-provenance", message_id="m71-provenance", text=OFFICIAL_FIXTURE))
    task = (await env["tasks"].list_for_source(source.id))[0]
    extraction = (await env["extractions"].list_for_message("m71-provenance"))[0]
    assert {task.source_id, task.source_message_id, task.source_text_reference} == {source.id, "m71-provenance", OFFICIAL_FIXTURE}
    normalized = json.loads(extraction.normalized_result)
    assert normalized["title"] == task.title
    assert normalized["course"] == task.course
    assert normalized["category"] == task.category


@pytest.mark.asyncio
async def test_m7_a06_agent_answers_after_canonical_task_tool_call(env):
    from campuscue.tools.task_tools import register_task_tools

    source = await env["sources"].create(platform="onebot", conversation_id="m71-agent", name="高数课程群")
    task = await env["task_service"].create_manual_task(
        title="高等数学第三章作业",
        category="homework",
        course="高等数学",
        deadline=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc),
        source_id=source.id,
    )

    class AgentProvider:
        model = "m71-agent-deterministic"
        max_context_tokens = 4096

        def __init__(self):
            self.requests = []

        async def chat(self, request):
            self.requests.append(request)
            if len(self.requests) == 1:
                return LLMResponse(
                    role="assistant",
                    content="",
                    usage={},
                    raw={},
                    tool_calls=(LLMToolCall("m71-call", "task_list", {"scope": "open"}),),
                )
            return LLMResponse(role="assistant", content="高等数学第三章作业截止 8 月 28 日 22:00。", usage={}, raw={})

    provider = AgentProvider()
    registry = ToolRegistry()
    register_task_tools(registry, task_service=env["task_service"], reminder_service=env["reminder_service"], tz=TZ, clock=FixedClock(NOW))
    runtime = CampusAgentRuntime(tools=registry, provider=provider, timezone=TZ, max_context_tokens=4096)
    reply = await runtime.chat(
        context=AgentContext(
            platform="onebot", source_id=source.id, conversation_id="m71-agent-thread",
            conversation_type=ConversationType.GROUP, message_id="m71-agent-query",
            timestamp=NOW, trace_id="m71-agent-trace", timezone=TZ, user_text="高数作业什么时候截止？",
        ),
        user_text="高数作业什么时候截止？",
    )
    assert task.id > 0 and "22:00" in reply
    assert provider.requests[0].messages[-1].role == "user"
    assert provider.requests[0].tools and any(tool.name == "task_list" for tool in provider.requests[0].tools)
    assert provider.requests[1].messages[-1].role == "tool"
    assert "高等数学第三章作业" in provider.requests[1].messages[-1].content


@pytest.mark.asyncio
async def test_m7_a07_cross_source_task_leakage_is_zero(env):
    source_a = await env["sources"].create(platform="onebot", conversation_id="m71-source-a")
    source_b = await env["sources"].create(platform="onebot", conversation_id="m71-source-b")
    task_b = await env["task_service"].create_manual_task(title="只属于 B 的任务", source_id=source_b.id)
    registry = ToolRegistry()
    register_task_tools(registry, task_service=env["task_service"], reminder_service=env["reminder_service"], tz=TZ, clock=FixedClock(NOW))
    result = await registry.execute(
        "task_list", arguments={"scope": "open"}, context=ToolContext(
            platform="onebot", source_id=source_a.id, conversation_id="m71-a",
            conversation_type=ConversationType.GROUP, message_id="m71-a-query", timestamp=NOW,
            trace_id="m71-a-trace", timezone=TZ, user_text="查任务",
        ),
    )
    assert result.ok
    assert "只属于 B 的任务" not in result.content
    assert task_b.id > 0


@pytest.mark.asyncio
async def test_m7_fake_reminder_boundary_observer_exposes_facts_without_qq_delivery(env):
    source = await env["sources"].create(platform="onebot", conversation_id="m71-reminder")
    task = await env["task_service"].create_manual_task(
        title="提醒边界测试",
        source_id=source.id,
        deadline=datetime(2026, 8, 25, 14, 0, tzinfo=timezone.utc),
    )

    class Sink:
        def __init__(self):
            self.received = []

        async def deliver(self, *, reminder, task):
            self.received.append((reminder.id, task.id, task.source_id))

    sink = Sink()
    env["reminder_service"].set_delivery(sink)
    reminder = (await env["reminders"].list_for_task(task.id))[0]
    assert await env["reminder_service"].fire(reminder.id) is True
    assert sink.received == [(reminder.id, task.id, source.id)]
