"""M2b.1.1 Real-Gate Hardening regression tests (external review round).

Covers:
- ContextCollector window RESIZE (Finding E)
- config fail-fast: test-DB isolation, confidence_threshold, timezone (Finding G)
- TaskService ownership cleanup: no _confidence_threshold, no dead
  decide_pending_confirm; TaskPipeline has no dead _dedup / no TaskService
  private access (Findings 13/14)
- extraction audit provider/model (Finding B) + model_said_none (Finding C)
  + generic INVALID_REQUEST no-fallback (Finding D) at the PIPELINE level
All deterministic (FixedClock), real SQLite, Mock transport — never the Internet.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.core.events import CampusEvent, ConversationType, EventType

TZ = ZoneInfo("Asia/Shanghai")
EVENT_TIME = datetime(2026, 8, 9, 16, 0, 0, tzinfo=timezone.utc)  # Mon 2026-08-10 00:00 +08


def _group_event(*, conversation="g1", text, message_id):
    return CampusEvent(
        event_id=f"e-{message_id}", trace_id=f"t-{message_id}", platform="onebot", adapter_id="a",
        event_type=EventType.GROUP_MESSAGE, self_id="10001", message_id=message_id,
        conversation_id=conversation, conversation_type=ConversationType.GROUP,
        sender_id="5", sender_name="", text=text, timestamp=EVENT_TIME,
    )


def _resp(content):
    return httpx.Response(200, json={
        "choices": [{"message": {"role": "assistant", "content": content}}], "usage": {},
    })


def _mock_provider(handler):
    from campuscue.providers.openai_compatible import OpenAICompatibleProvider

    return OpenAICompatibleProvider(
        base_url="https://mock/v1", model="mock-model",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


class _FakeManager:
    def __init__(self, provider):
        self._provider = provider

    async def get_default(self):
        return self._provider


@pytest.fixture
async def env(tmp_path):
    from campuscue.repositories.repositories import (
        ExtractionRepository,
        SourceRepository,
        TaskRepository,
    )
    from campuscue.services.task_service import TaskService
    from campuscue.storage.clock import FixedClock
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.pipeline import TaskPipeline

    database = Database(DatabaseConfig(path=tmp_path / "h.db", env="test"))
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
        timezone=TZ,
        clock=clock,
    )
    yield {"db": database, "sources": sources, "tasks": tasks,
           "extractions": extractions, "pipeline": pipeline}
    await database.dispose()


# ------------------------------------------------------------------ Finding E: context window resize

class TestContextWindowResize:
    @pytest.mark.asyncio
    async def test_window_grows_after_resize(self, env):
        """window=1 -> observe -> resize to 3 -> subsequent 3 messages are all
        retained as previous context (old maxlen no longer caps the ring)."""
        from campuscue.tasks.context import ContextCollector

        collector = ContextCollector()
        e1 = _group_event(text="m1", message_id="1")
        e2 = _group_event(text="m2", message_id="2")
        e3 = _group_event(text="m3", message_id="3")
        e4 = _group_event(text="m4", message_id="4")
        e5 = _group_event(text="m5", message_id="5")

        collector.observe(e1, source_id=1, context_window=1)
        collector.observe(e2, source_id=1, context_window=1)
        # window=1: only m2 retained -> snapshot before resize
        assert collector.snapshot(e3, context_window=1) == ["m2"]

        # resize to 3: buffer maxlen must become 3 (m2 survives the resize)
        collector.observe(e3, source_id=1, context_window=3)
        snap = collector.snapshot(e4, context_window=3)
        assert snap == ["m2", "m3"]  # m1 was already discarded — acceptable

        # subsequent messages allow growth to the full 3
        collector.observe(e4, source_id=1, context_window=3)
        collector.observe(e5, source_id=1, context_window=3)
        snap = collector.snapshot(_group_event(text="m6", message_id="6"), context_window=3)
        assert snap == ["m3", "m4", "m5"]

    @pytest.mark.asyncio
    async def test_window_shrinks_safely(self, env):
        from campuscue.tasks.context import ContextCollector

        collector = ContextCollector()
        events = [_group_event(text=f"m{i}", message_id=str(i)) for i in range(1, 6)]
        for e in events:
            collector.observe(e, source_id=1, context_window=5)
        assert collector.snapshot(_group_event(text="m6", message_id="6"), context_window=5) == ["m1", "m2", "m3", "m4", "m5"]
        # shrink to 2: only the 2 newest retained
        collector.observe(_group_event(text="m6", message_id="6"), source_id=1, context_window=2)
        assert collector.snapshot(_group_event(text="m7", message_id="7"), context_window=2) == ["m5", "m6"]

    @pytest.mark.asyncio
    async def test_cross_source_isolation_preserved(self, env):
        from campuscue.tasks.context import ContextCollector

        collector = ContextCollector()
        collector.observe(_group_event(conversation="g1", text="高数", message_id="a1"), source_id=1, context_window=3)
        collector.observe(_group_event(conversation="g2", text="英语", message_id="b1"), source_id=2, context_window=1)
        # resize g1 -> 3 must not affect g2's window=1
        collector.observe(_group_event(conversation="g1", text="高数2", message_id="a2"), source_id=1, context_window=3)
        snap_g1 = collector.snapshot(_group_event(conversation="g1", text="高数3", message_id="a3"), context_window=3)
        assert snap_g1 == ["高数", "高数2"]
        snap_g2 = collector.snapshot(_group_event(conversation="g2", text="英语2", message_id="b2"), context_window=1)
        assert snap_g2 == ["英语"]


# ------------------------------------------------------------------ Finding G: config fail-fast

class TestConfigTestIsolation:
    def test_test_env_pipeline_no_db_path_fails(self, monkeypatch):
        """CAMPUSCUE_ENV=test + pipeline enabled + NO CAMPUSCUE_DB_PATH -> FAIL
        before any DB open (no automatic route to the application DB)."""
        from campuscue.config import ConfigError, load_config

        monkeypatch.setenv("CAMPUSCUE_ENV", "test")
        monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
        monkeypatch.delenv("CAMPUSCUE_DB_PATH", raising=False)
        with pytest.raises(ConfigError, match="CAMPUSCUE_DB_PATH"):
            load_config()

    def test_test_env_pipeline_explicit_db_path_passes(self, monkeypatch, tmp_path):
        from campuscue.config import load_config

        monkeypatch.setenv("CAMPUSCUE_ENV", "test")
        monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
        monkeypatch.setenv("CAMPUSCUE_DB_PATH", str(tmp_path / "t.db"))
        cfg = load_config()
        assert cfg.tasks.database_path == str(tmp_path / "t.db")
        assert cfg.tasks.database_path_explicit is True

    def test_production_default_still_allowed(self, monkeypatch):
        from campuscue.config import load_config

        monkeypatch.delenv("CAMPUSCUE_ENV", raising=False)
        monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
        monkeypatch.delenv("CAMPUSCUE_DB_PATH", raising=False)
        cfg = load_config()
        assert cfg.tasks.database_path == "data/campuscue.db"

    def test_pipeline_disabled_test_env_no_db_path_ok(self, monkeypatch):
        """M1-compatible: pipeline disabled -> no test-DB requirement."""
        from campuscue.config import load_config

        monkeypatch.setenv("CAMPUSCUE_ENV", "test")
        monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "0")
        monkeypatch.delenv("CAMPUSCUE_DB_PATH", raising=False)
        cfg = load_config()
        assert cfg.tasks.enabled is False

    def test_invalid_confidence_threshold_rejected(self, monkeypatch):
        from campuscue.config import ConfigError, load_config

        for bad in ("-0.1", "1.5", "nan", "inf"):
            monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
            monkeypatch.setenv("CAMPUSCUE_CONFIDENCE_THRESHOLD", bad)
            monkeypatch.setenv("CAMPUSCUE_DB_PATH", "C:/tmp/explicit.db")
            with pytest.raises(ConfigError, match="confidence_threshold"):
                load_config()

    def test_valid_confidence_threshold_bounds(self, monkeypatch):
        from campuscue.config import load_config

        for good in ("0.0", "0.6", "1.0"):
            monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
            monkeypatch.setenv("CAMPUSCUE_CONFIDENCE_THRESHOLD", good)
            monkeypatch.setenv("CAMPUSCUE_DB_PATH", "C:/tmp/explicit.db")
            assert load_config().tasks.confidence_threshold == float(good)

    def test_invalid_timezone_rejected(self, monkeypatch):
        from campuscue.config import ConfigError, load_config

        monkeypatch.setenv("CAMPUSCUE_TASK_PIPELINE", "1")
        monkeypatch.setenv("CAMPUSCUE_TIMEZONE", "Not/A_Zone")
        monkeypatch.setenv("CAMPUSCUE_DB_PATH", "C:/tmp/explicit.db")
        with pytest.raises(ConfigError, match="timezone"):
            load_config()


# ------------------------------------------------------------------ Findings 13/14: ownership cleanup

class TestOwnershipCleanup:
    def test_task_service_has_no_confidence_threshold(self):
        """TaskService no longer stores/recomputes confidence (pipeline owns L4/L6)."""
        import inspect

        from campuscue.services import task_service as ts

        src = inspect.getsource(ts)
        assert "confidence_threshold" not in src
        assert "decide_pending_confirm" not in src  # dead helper gone

    def test_pipeline_no_dead_dedup_object(self):
        """TaskPipeline no longer constructs its own Deduplicator over
        TaskService._tasks (private access removed; TaskService remains the
        authoritative dedup/create boundary)."""
        import inspect

        from campuscue.tasks import pipeline as p

        src = inspect.getsource(p)
        assert "task_service._tasks" not in src
        assert "self._dedup" not in src


# ------------------------------------------------------------------ Findings B/C/D at pipeline level

class TestExtractionProviderModelAudit:
    @pytest.mark.asyncio
    async def test_task_created_records_provider_model(self, env):
        await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = lambda req: _resp(json.dumps({
            "has_task": True, "category": "homework", "title": "作业",
            "deadline_phrase": "周五", "confidence": 0.9, "reason": "x",
        }))
        env["pipeline"]._provider_manager = _FakeManager(_mock_provider(handler))
        await env["pipeline"].handle(_group_event(text="作业周五交", message_id="m-ok"))
        ex = (await env["extractions"].list_for_message("m-ok"))[0]
        assert ex.status == "success"
        assert ex.provider == "openai_compatible"
        assert ex.model == "mock-model"

    @pytest.mark.asyncio
    async def test_model_said_none_records_provider_model_and_reason(self, env):
        await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = lambda req: _resp(json.dumps({
            "has_task": False, "confidence": 0.94, "reason": "普通聊天",
        }))
        env["pipeline"]._provider_manager = _FakeManager(_mock_provider(handler))
        await env["pipeline"].handle(_group_event(text="你吃饭了吗", message_id="m-none"))
        ex = (await env["extractions"].list_for_message("m-none"))[0]
        assert ex.status == "skipped"
        assert ex.provider == "openai_compatible"
        assert ex.model == "mock-model"
        assert ex.confidence == 0.94  # confidence persisted on the row
        # normalized_result contains has_task/confidence/reason, no Task fields
        norm = json.loads(ex.normalized_result)
        assert norm == {"has_task": False, "confidence": 0.94, "reason": "普通聊天"}
        # audit.l3 retains the same safe fields
        audit = json.loads(ex.audit)
        assert audit["l3"]["has_task"] is False
        assert audit["l3"]["confidence"] == 0.94
        assert audit["l3"]["reason"] == "普通聊天"
        # privacy: input text NOT persisted anywhere on the skipped row
        assert "你吃饭了吗" not in (ex.raw_result or "")
        assert "你吃饭了吗" not in (ex.audit or "")
        assert "你吃饭了吗" not in (ex.normalized_result or "")
        assert "你吃饭了吗" not in (ex.error or "")

    @pytest.mark.asyncio
    async def test_duplicate_records_provider_model(self, env):
        await env["sources"].create(platform="onebot", conversation_id="g1")
        handler = lambda req: _resp(json.dumps({
            "has_task": True, "category": "homework", "title": "作业",
            "deadline_phrase": "周五", "confidence": 0.9, "reason": "重复",
        }))
        env["pipeline"]._provider_manager = _FakeManager(_mock_provider(handler))
        await env["pipeline"].handle(_group_event(text="作业周五交", message_id="d1"))
        await env["pipeline"].handle(_group_event(text="作业周五交", message_id="d2"))
        ex = (await env["extractions"].list_for_message("d2"))[0]
        assert ex.status == "duplicate"
        assert ex.provider == "openai_compatible"
        assert ex.model == "mock-model"

    @pytest.mark.asyncio
    async def test_no_provider_selection_error_has_null_provider_model(self, env):
        """Provider selection failure BEFORE a provider exists -> provider/model
        may be null (allowed by the contract)."""
        from campuscue.providers.errors import NoProviderConfiguredError

        await env["sources"].create(platform="onebot", conversation_id="g1")

        class EmptyManager:
            async def get_default(self):
                raise NoProviderConfiguredError()

        env["pipeline"]._provider_manager = EmptyManager()
        await env["pipeline"].handle(_group_event(text="作业周五交", message_id="m-noprov"))
        ex = (await env["extractions"].list_for_message("m-noprov"))[0]
        assert ex.status == "error"
        assert ex.provider is None
        assert ex.model is None
        assert ex.error == "no_provider_configured"

    @pytest.mark.asyncio
    async def test_generic_invalid_request_no_fallback_pipeline(self, env):
        """Pipeline-level (Finding D): a generic 400 invalid parameter -> 1 call
        only, no schema fallback."""
        from campuscue.providers.errors import ProviderError, ProviderErrorCode

        await env["sources"].create(platform="onebot", conversation_id="g1")
        calls = []

        def handler(req):
            calls.append(1)
            raise ProviderError(ProviderErrorCode.INVALID_REQUEST, "bad param")

        env["pipeline"]._provider_manager = _FakeManager(_mock_provider(handler))
        await env["pipeline"].handle(_group_event(text="作业周五交", message_id="m-g400"))
        assert len(calls) == 1  # NO fallback
        ex = (await env["extractions"].list_for_message("m-g400"))[0]
        assert ex.status == "error"
        assert ex.error == "provider:invalid_request"
