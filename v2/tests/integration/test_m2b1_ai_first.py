"""M2b.1 AI-first regression tests (ADR-013).

Core invariant: normal natural-language messages ALWAYS reach the LLM even with
local signal score 0; local rules only hard-drop certain garbage. Ambiguous,
context-dependent messages must not be killed locally.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest

from zoneinfo import ZoneInfo

from campuscue.core.events import CampusEvent, ConversationType, EventType
from campuscue.storage.enums import ExtractionStatus
from campuscue.tasks.prefilter import analyze_signals, hygiene_check

EVENT_TIME = datetime(2026, 8, 9, 16, 0, 0, tzinfo=timezone.utc)


def _group_event(*, conversation="g1", text, message_id):
    return CampusEvent(
        event_id=f"e-{message_id}", trace_id=f"t-{message_id}", platform="onebot", adapter_id="a",
        event_type=EventType.GROUP_MESSAGE, self_id="10001", message_id=message_id,
        conversation_id=conversation, conversation_type=ConversationType.GROUP,
        sender_id="5", sender_name="", text=text, timestamp=EVENT_TIME,
    )


@pytest.fixture
async def ai_env(tmp_path):
    """Real DB + repos + TaskService + pipeline with injectable fake manager."""
    from campuscue.repositories.repositories import (
        ExtractionRepository,
        SourceRepository,
        TaskRepository,
    )
    from campuscue.services.task_service import TaskService
    from campuscue.storage.clock import FixedClock
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.pipeline import TaskPipeline

    database = Database(DatabaseConfig(path=tmp_path / "ai.db", env="test"))
    await database.initialize()
    sources = SourceRepository(database.session)
    tasks = TaskRepository(database.session)
    extractions = ExtractionRepository(database.session)
    clock = FixedClock(datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc))
    pipeline = TaskPipeline(
        sources=sources,
        extractions=extractions,
        task_service=TaskService(tasks, clock=clock),
        provider_manager=None,
        timezone=ZoneInfo("Asia/Shanghai"),
        clock=clock,
    )
    yield {"db": database, "sources": sources, "tasks": tasks,
           "extractions": extractions, "pipeline": pipeline, "clock": clock}
    await database.dispose()


def _fake_manager(handler):
    from campuscue.providers.openai_compatible import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        base_url="https://mock/v1", model="mock-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    class M:
        async def get_default(self):
            return provider

    return M()


def _resp(content):
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}], "usage": {},
    })


class TestLowSignalReachesLLM:
    """§54/§58: local signal score must NEVER block LLM access."""

    @pytest.mark.asyncio
    async def test_zero_or_low_signal_still_calls_provider(self, ai_env):
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        def handler(request):
            calls.append(1)
            return _resp(json.dumps({"has_task": False}))

        env["pipeline"]._provider_manager = _fake_manager(handler)
        # "这个周五前交一下" — minimal local signals but valid natural language
        signals = analyze_signals("这个周五前交一下")
        assert signals.score > 0  # time present; still assert provider called
        await env["pipeline"].handle(_group_event(conversation="g1", text="这个周五前交一下", message_id="m-low"))
        assert len(calls) == 1  # provider called exactly once

    @pytest.mark.asyncio
    async def test_ambiguous_message_reaches_llm(self, ai_env):
        """§66-A/B/C/D: ambiguous context-dependent messages must reach LLM."""
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        for text in [
            "这个周五前交一下",
            "还是按之前那个时间",
            "下周一上课的时候带过来",
            "报名表今晚就关了",
        ]:
            assert hygiene_check(text).passed is True  # not killed locally

    @pytest.mark.asyncio
    async def test_context_resolves_ambiguous_task(self, ai_env):
        """§55: Message1 '高数第三章' observed; Message2 resolves via context."""
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1", context_window=5)
        seen = {}

        def handler(request):
            seen["body"] = json.loads(request.content)
            return _resp(json.dumps({
                "has_task": True, "category": "homework", "title": "第三章作业",
                "course": "高等数学", "deadline_phrase": "周五前", "submission_method": "学习通",
                "confidence": 0.85, "reason": "结合上下文确定",
            }))

        env["pipeline"]._provider_manager = _fake_manager(handler)
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数第三章", message_id="m-ctx1"))
        await env["pipeline"].handle(_group_event(conversation="g1", text="这个周五前交学习通", message_id="m-ctx2"))

        user_content = seen["body"]["messages"][-1]["content"]
        assert "高数第三章" in user_content  # previous context included
        assert user_content.count("这个周五前交学习通") == 1  # current exactly once
        tasks = await env["tasks"].list_all()
        assert len(tasks) == 1
        assert tasks[0].title == "第三章作业"
        assert tasks[0].course == "高等数学"

    @pytest.mark.asyncio
    async def test_normal_chat_goes_to_model_and_skipped(self, ai_env):
        """§56: normal chat reaches LLM -> has_task=false -> 1 skipped Extraction, 0 Task."""
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        def handler(request):
            calls.append(1)
            return _resp(json.dumps({"has_task": False}))

        env["pipeline"]._provider_manager = _fake_manager(handler)
        await env["pipeline"].handle(_group_event(conversation="g1", text="你吃饭了吗", message_id="m-chat"))
        assert len(calls) == 1
        assert await env["tasks"].list_all() == []
        ex = await env["extractions"].list_for_message("m-chat")
        assert len(ex) == 1 and ex[0].status == ExtractionStatus.SKIPPED.value


class TestHygieneOnlyCertainGarbage:
    @pytest.mark.asyncio
    async def test_garbage_hard_drop_no_provider(self, ai_env):
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        class Boom:
            async def get_default(self):
                calls.append("provider")
                raise AssertionError("provider must not be called on hygiene drop")

        env["pipeline"]._provider_manager = Boom()
        for text, mid in [("   ", "m-g1"), ("", "m-g2"), ("😀✨", "m-g3")]:
            await env["pipeline"].handle(_group_event(conversation="g1", text=text, message_id=mid))
        assert calls == []
        assert await env["tasks"].list_all() == []
        assert await env["extractions"].list_for_message("m-g1") == []


class TestSingleCallTriage:
    @pytest.mark.asyncio
    async def test_single_call_normal_path(self, ai_env):
        """§24: normal path = exactly 1 provider call (triage + extraction together)."""
        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        def handler(request):
            calls.append(1)
            return _resp(json.dumps({
                "has_task": True, "category": "homework", "title": "作业",
                "deadline_phrase": "周五晚上12点前", "confidence": 0.9,
            }))

        env["pipeline"]._provider_manager = _fake_manager(handler)
        await env["pipeline"].handle(_group_event(conversation="g1", text="作业周五晚上12点前交", message_id="m-1call"))
        assert len(calls) == 1  # triage + extraction in one call
        assert len(await env["tasks"].list_all()) == 1

    @pytest.mark.asyncio
    async def test_fallback_max_two_calls(self, ai_env):
        """§23/24: schema INVALID_REQUEST -> exactly one fallback (2 calls total, never 3)."""
        from campuscue.providers.errors import ProviderError, ProviderErrorCode

        env = ai_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                raise ProviderError(ProviderErrorCode.INVALID_REQUEST, "json_schema unsupported")
            return _resp(json.dumps({"has_task": True, "title": "作业F", "confidence": 0.9}))

        env["pipeline"]._provider_manager = _fake_manager(handler)
        await env["pipeline"].handle(_group_event(conversation="g1", text="作业周五交", message_id="m-fb"))
        assert len(calls) == 2  # hard cap
        assert len(await env["tasks"].list_all()) == 1
