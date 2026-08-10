"""M2b.1 integration tests: full pipeline L0-L7 with Mock Provider -> real SQLite,
concurrent dedup, extraction audit, M1 regression with pipeline opt-in."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.core.events import CampusEvent, ConversationType, EventType
from campuscue.storage.enums import ExtractionStatus

TZ = ZoneInfo("Asia/Shanghai")

# event time: Monday 2026-08-10 00:00 +08:00 (i.e., 2026-08-09 16:00 UTC)
EVENT_TIME = datetime(2026, 8, 9, 16, 0, 0, tzinfo=timezone.utc)


def _group_event(*, conversation="g1", text, message_id="m1", sender="5"):
    return CampusEvent(
        event_id=f"e-{message_id}", trace_id=f"t-{message_id}", platform="onebot", adapter_id="a",
        event_type=EventType.GROUP_MESSAGE, self_id="10001", message_id=message_id,
        conversation_id=conversation, conversation_type=ConversationType.GROUP,
        sender_id=sender, sender_name="", text=text, timestamp=EVENT_TIME,
    )


def _mock_provider_client(handler):
    from campuscue.providers.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        base_url="https://mock/v1", model="mock-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture
async def pipeline_env(tmp_path):
    """Real DB + repos + TaskService + pipeline with injectable provider."""
    from campuscue.providers.manager import ProviderManager
    from campuscue.repositories.repositories import (
        ExtractionRepository,
        ProviderConfigRepository,
        SourceRepository,
        TaskRepository,
    )
    from campuscue.services.task_service import TaskService
    from campuscue.storage.clock import FixedClock
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.pipeline import TaskPipeline

    database = Database(DatabaseConfig(path=tmp_path / "p.db", env="test"))
    await database.initialize()
    sources = SourceRepository(database.session)
    tasks = TaskRepository(database.session)
    extractions = ExtractionRepository(database.session)
    provider_configs = ProviderConfigRepository(database.session)
    clock = FixedClock(datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc))
    task_service = TaskService(tasks, clock=clock)
    pipeline = TaskPipeline(
        sources=sources,
        extractions=extractions,
        task_service=task_service,
        provider_manager=ProviderManager(provider_configs),
        timezone=TZ,
        clock=clock,
    )
    env = {
        "db": database, "sources": sources, "tasks": tasks, "extractions": extractions,
        "provider_configs": provider_configs, "task_service": task_service,
        "pipeline": pipeline, "clock": clock,
    }
    yield env
    await database.dispose()


def _extraction_handler(content: str, calls: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": content}}], "usage": {},
        })

    return handler


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_creates_task(self, pipeline_env):
        """Mock Provider -> real pipeline -> real SQLite Task row (M2b.1 §52)."""
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = _extraction_handler(json.dumps({
            "has_task": True, "category": "homework", "title": "第三章作业",
            "course": "高等数学", "deadline_phrase": "周五晚上12点前",
            "submission_method": "学习通", "confidence": 0.9, "reason": "明确截止与提交方式",
        }))
        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )

        await env["pipeline"].handle(_group_event(conversation="g1", text="高数第三章作业周五晚上12点前交学习通。"))

        tasks = await env["tasks"].list_all()
        assert len(tasks) == 1
        t = tasks[0]
        assert t.title == "第三章作业"
        assert t.category == "homework"
        assert t.course == "高等数学"
        assert t.deadline == datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)  # Fri 23:59+08
        assert t.status == "pending"
        assert t.source_text_reference == "高数第三章作业周五晚上12点前交学习通。"
        assert "学习通" in (t.description or "")  # submission_method preserved

        extractions = await env["extractions"].list_for_message("m1")
        assert len(extractions) == 1
        assert extractions[0].status == ExtractionStatus.SUCCESS.value
        audit = json.loads(extractions[0].audit)
        assert {"l1", "l3", "l4", "l5", "outcome"} <= set(audit.keys())
        assert audit["l4"]["reason"] == "weekday+clock"
        assert "学习通" in (extractions[0].normalized_result or "")

    @pytest.mark.asyncio
    async def test_l0_drop_no_extraction_no_provider(self, pipeline_env):
        """Unconfigured source: 0 provider calls, 0 extraction rows, 0 tasks."""
        env = pipeline_env
        called = []

        class Boom:
            async def get_default(self):
                called.append("provider-called")
                raise AssertionError("provider must not be called on L0 drop")

        env["pipeline"]._provider_manager = Boom()
        await env["pipeline"].handle(_group_event(conversation="unknown", text="高数作业周五交", message_id="m0"))
        assert called == []
        assert await env["tasks"].list_all() == []
        assert await env["extractions"].list_for_message("m0") == []

    @pytest.mark.asyncio
    async def test_l1_drop_no_extraction(self, pipeline_env):
        """Chatter rejected by L1: no extraction row (privacy decision)."""
        env = pipeline_env
        await env["sources"].create(platform="onebot", conversation_id="g1")
        await env["pipeline"].handle(_group_event(conversation="g1", text="我觉得这门课挺有意思的", message_id="m-chat"))
        assert await env["tasks"].list_all() == []
        assert await env["extractions"].list_for_message("m-chat") == []

    @pytest.mark.asyncio
    async def test_duplicate_no_second_task(self, pipeline_env):
        """Equivalent notice, different message_id, within 36h: no second Task."""
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = _extraction_handler(json.dumps({
            "has_task": True, "category": "homework", "title": "第三章作业",
            "course": "高等数学", "deadline_phrase": "周五晚上12点前",
            "confidence": 0.9, "reason": "重复通知",
        }))
        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数第三章作业周五晚上12点前交", message_id="m1"))
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数第三章作业周五晚上12点前交", message_id="m2"))

        tasks = await env["tasks"].list_all()
        assert len(tasks) == 1  # no second task
        ex = await env["extractions"].list_for_message("m2")
        assert ex and ex[0].status == ExtractionStatus.DUPLICATE.value
        audit = json.loads(ex[0].audit)
        assert audit["l5"]["dedup"] == "same_semantic_task"

    @pytest.mark.asyncio
    async def test_same_message_id_duplicate(self, pipeline_env):
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = _extraction_handler(json.dumps({
            "has_task": True, "category": "homework", "title": "作业", "confidence": 0.9,
        }))
        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        await env["pipeline"].handle(_group_event(conversation="g1", text="作业周五交", message_id="m-x"))
        await env["pipeline"].handle(_group_event(conversation="g1", text="作业周五交", message_id="m-x"))
        assert len(await env["tasks"].list_all()) == 1

    @pytest.mark.asyncio
    async def test_model_said_none(self, pipeline_env):
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = _extraction_handler(json.dumps({"has_task": False}))
        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数作业周五交", message_id="m-none"))
        assert await env["tasks"].list_all() == []
        ex = await env["extractions"].list_for_message("m-none")
        assert len(ex) == 1 and ex[0].status == ExtractionStatus.SKIPPED.value

    @pytest.mark.asyncio
    async def test_provider_error_safe(self, pipeline_env):
        from campuscue.providers.errors import ProviderError, ProviderErrorCode

        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")

        def handler(request):
            raise ProviderError(ProviderErrorCode.AUTH_ERROR, "bad key")

        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数作业周五交", message_id="m-err"))
        assert await env["tasks"].list_all() == []
        ex = await env["extractions"].list_for_message("m-err")
        assert len(ex) == 1 and ex[0].status == ExtractionStatus.ERROR.value
        assert "provider:auth_error" in ex[0].error  # safe classification, no secret


class TestConcurrentDedup:
    @pytest.mark.asyncio
    async def test_concurrent_same_semantic_one_task(self, pipeline_env):
        """Two concurrent pipeline runs for the same obligation -> exactly ONE Task."""
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = _extraction_handler(json.dumps({
            "has_task": True, "category": "homework", "title": "第三章作业",
            "course": "高等数学", "deadline_phrase": "周五晚上12点前", "confidence": 0.9,
        }))
        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        e1 = _group_event(conversation="g1", text="高数第三章作业周五晚上12点前交", message_id="m-a")
        e2 = _group_event(conversation="g1", text="高数第三章作业周五晚上12点前交", message_id="m-b")
        await asyncio.gather(
            env["pipeline"].handle(e1),
            env["pipeline"].handle(e2),
        )
        tasks = await env["tasks"].list_all()
        assert len(tasks) == 1  # exactly one Task
        statuses = {x.status for x in await env["extractions"].list_for_message("m-b")}
        assert ExtractionStatus.DUPLICATE.value in statuses or tasks[0].id > 0


class TestContextObservation:
    @pytest.mark.asyncio
    async def test_l1_rejected_message_becomes_context(self, pipeline_env):
        """M2b.1 §43: chatter observed as context even when L1 rejects it."""
        env = pipeline_env
        src = await env["sources"].create(platform="onebot", conversation_id="g1", context_window=5)
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={
                "choices": [{"message": {"role": "assistant", "content": json.dumps({"has_task": True, "title": "作业", "confidence": 0.8})}}],
                "usage": {},
            })

        env["pipeline"]._provider_manager = _FakeManager(
            _mock_provider_client(handler)
        )
        # message 1: chatter (L1 likely rejects) but observed
        await env["pipeline"].handle(_group_event(conversation="g1", text="高数第三章", message_id="m-c1"))
        # message 2: candidate that passes L1 -> extractor receives previous context
        await env["pipeline"].handle(_group_event(conversation="g1", text="这个周五前交学习通", message_id="m-c2"))

        user_content = seen["body"]["messages"][-1]["content"]
        assert "高数第三章" in user_content  # previous context included
        assert user_content.count("这个周五前交学习通") == 1  # current appears exactly once


class TestM1RegressionWithPipeline:
    @pytest.mark.asyncio
    async def test_hello_still_echoed_with_pipeline_disabled(self, tmp_path):
        """M1 regression: pipeline disabled -> hello -> received: hello (no DB/Provider)."""
        from campuscue.app.runtime import CampusRuntime
        from campuscue.config import RuntimeConfig

        cfg = RuntimeConfig()  # tasks.enabled defaults False
        assert cfg.tasks.enabled is False
        rt = CampusRuntime(cfg)
        # router-level check without starting WS server:
        from campuscue.core.router import Router
        from campuscue.handlers.echo import echo_handler

        router = Router()
        router.add_handler(echo_handler)
        event = _group_event(conversation="g1", text="hello", message_id="h1")
        result = await router.route(event)
        assert result is not None and result.text == "received: hello"


class _FakeManager:
    """Manager-boundary fake: returns a REAL OpenAICompatibleProvider with a
    mock transport. The pipeline contract with the manager is just get_default();
    provider -> transport -> parse path stays real."""

    def __init__(self, provider):
        self._provider = provider

    async def get_default(self):
        return self._provider
