"""M7-A10 local deterministic full-loop acceptance harness."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.core.events import CampusEvent, ConversationType, EventType
from campuscue.providers.models import LLMResponse, LLMToolCall
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.storage.clock import FixedClock
from campuscue.tools.registry import ToolRegistry
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
OFFICIAL_FIXTURE = "高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。"


def _event() -> CampusEvent:
    return CampusEvent(
        event_id="m73-demo-event",
        trace_id="m73-demo-trace",
        platform="onebot",
        adapter_id="m73-demo-adapter",
        event_type=EventType.GROUP_MESSAGE,
        self_id="synthetic-bot",
        message_id="m73-demo-message",
        conversation_id="m73-demo-group",
        conversation_type=ConversationType.GROUP,
        sender_id="synthetic-student",
        sender_name="",
        text=OFFICIAL_FIXTURE,
        timestamp=NOW,
    )


def _extraction_provider() -> OpenAICompatibleProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        result = {
            "has_task": True,
            "category": "homework",
            "title": "高等数学第三章作业",
            "course": "高等数学",
            "deadline_phrase": "2026年8月28日22:00前",
            "confidence": 0.96,
            "reason": "明确课程、事项与截止时间",
        }
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": json.dumps(result, ensure_ascii=False)}}], "usage": {}})

    return OpenAICompatibleProvider(
        base_url="https://m73.demo/v1",
        model="m73-demo-extraction",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


class _ProviderManager:
    def __init__(self, provider):
        self.provider = provider

    async def get_default(self):
        return self.provider


class _AgentProvider:
    model = "m73-demo-agent"
    max_context_tokens = 4096

    def __init__(self, task_id: int):
        self.task_id = task_id
        self.calls = 0

    async def chat(self, request):
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(role="assistant", content="", usage={}, raw={}, tool_calls=(LLMToolCall("read", "task_list", {"scope": "open"}),))
        if self.calls == 2:
            return LLMResponse(role="assistant", content="高等数学第三章作业截止 8 月 28 日 22:00。", usage={}, raw={})
        return LLMResponse(
            role="assistant",
            content="",
            usage={},
            raw={},
            tool_calls=(LLMToolCall("update", "task_update", {"task_id": self.task_id, "deadline_phrase": "2026年8月29日22:00前"}),),
        )


@pytest.mark.asyncio
async def test_m7_a10_local_deterministic_full_loop(tmp_path):
    started = time.perf_counter()
    steps = [
        "Step 0 clean start",
        "Step 1 source configured",
        "Step 2 source connection state visible",
        "Step 3 official message enters",
        "Step 4 extraction",
        "Step 5 provenance/confidence visible",
        "Step 6 canonical task",
        "Step 7 reminder scheduled",
        "Step 8 Agent read question",
        "Step 9 canonical tool result",
        "Step 10 Agent grounded answer",
        "Step 11 mutation proposal",
        "Step 12 user confirmation",
        "Step 13 TaskService mutation",
        "Step 14 Reminder lifecycle follows",
        "Step 15 synthetic reminder result",
        "Step 16 final state visible",
    ]
    from campuscue.providers.manager import ProviderManager
    from campuscue.repositories.repositories import ExtractionRepository, ProviderConfigRepository, ReminderRepository, SourceRepository, TaskRepository
    from campuscue.services.reminder_service import NoopScheduler, ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.pipeline import TaskPipeline
    from campuscue.tasks.reminder_policy import ReminderPolicy

    db = Database(DatabaseConfig(path=tmp_path / "m73-demo.db", env="test"))
    await db.initialize()
    try:
        clock = FixedClock(NOW)
        sources = SourceRepository(db.session, clock=clock)
        tasks = TaskRepository(db.session, clock=clock)
        reminders = ReminderRepository(db.session, clock=clock)
        extractions = ExtractionRepository(db.session, clock=clock)
        configs = ProviderConfigRepository(db.session, clock=clock)
        reminder_service = ReminderService(
            reminders, tasks, scheduler=NoopScheduler(), clock=clock, timezone=TZ,
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
        pipeline._provider_manager = _ProviderManager(_extraction_provider())
        source = await sources.create(platform="onebot", conversation_id="m73-demo-group", name="M7 Demo Group")
        assert source.enabled is True
        await pipeline.handle(_event())
        task = (await tasks.list_for_source(source.id))[0]
        extraction = (await extractions.list_for_message("m73-demo-message"))[0]
        assert task.title == "高等数学第三章作业"
        assert task.confidence == 0.96
        assert task.source_text_reference == OFFICIAL_FIXTURE
        assert (await reminders.list_for_task(task.id))

        agent_provider = _AgentProvider(task.id)
        registry = ToolRegistry()
        register_task_tools(registry, task_service=task_service, reminder_service=reminder_service, tz=TZ, clock=clock)
        runtime = CampusAgentRuntime(tools=registry, provider=agent_provider, timezone=TZ, clock=clock, max_context_tokens=4096)
        context = AgentContext(
            platform="onebot", source_id=source.id, conversation_id="m73-demo-thread",
            conversation_type=ConversationType.GROUP, message_id="m73-agent-read", timestamp=NOW,
            trace_id="m73-agent-trace", timezone=TZ, user_text="这周有什么任务？",
        )
        read = await runtime.chat_with_trace(context=context, user_text="这周有什么任务？")
        assert "截止" in read.message and "已查询当前来源的任务" in read.tool_activity
        proposal = await runtime.chat_with_trace(context=context, user_text="把截止改到周六晚上10点")
        assert proposal.confirmation_state == "pending"
        before = await tasks.get(task.id)
        assert before.deadline == datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc)
        confirmed = await runtime.chat_with_trace(
            context=AgentContext(**{**context.__dict__, "message_id": "m73-agent-confirm", "user_text": "确认"}),
            user_text="确认",
        )
        assert confirmed.confirmation_state == "confirmed"
        final_task = await tasks.get(task.id)
        assert final_task.deadline == datetime(2026, 8, 29, 14, 0, tzinfo=timezone.utc)
        current_reminders = [row for row in await reminders.list_for_task(task.id) if row.status == "scheduled"]
        assert current_reminders

        class Sink:
            def __init__(self): self.received = []
            async def deliver(self, *, reminder, task): self.received.append((reminder.id, task.id))

        sink = Sink()
        reminder_service.set_delivery(sink)
        assert await reminder_service.fire(current_reminders[-1].id) is True
        assert len(sink.received) == 1
        assert (await reminders.get(current_reminders[-1].id)).status == "fired"
        assert json.loads(extraction.audit)["l3"]["confidence"] == 0.96
        ended = time.perf_counter()
        duration = ended - started
        assert duration < 300
        evidence = Path(__file__).parents[3] / ".ai-handoff" / "evidence" / "m73" / "a10-local.json"
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({
            "kind": "LOCAL DETERMINISTIC FULL LOOP",
            "fixture": "official M7 fixture",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(duration, 4),
            "steps": steps,
            "tool_activity": read.tool_activity + proposal.tool_activity + confirmed.tool_activity,
            "reminder_delivery": "synthetic in-process sink",
            "real_qq": "NOT_RUN",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        await db.dispose()
