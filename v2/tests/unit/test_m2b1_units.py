"""M2b.1 unit tests: prefilter, source policy, time normalizer, dedup, extractor,
task service. All deterministic, no wall clock."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.tasks.prefilter import analyze_signals, hygiene_check
from campuscue.tasks.time_normalizer import resolve_deadline

TZ = ZoneInfo("Asia/Shanghai")
ANCHOR = datetime(2026, 8, 10, 0, 0, 0, tzinfo=TZ)  # Monday 2026-08-10 00:00 +08:00


@pytest.fixture
async def db_raw(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "u.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


# ------------------------------------------------------------------ Hygiene + Signals (AI-first)

class TestHygieneFilter:
    def test_empty_rejected(self):
        assert hygiene_check("").passed is False
        assert hygiene_check("   ").passed is False
        assert hygiene_check(None).passed is False

    def test_oversized_rejected(self):
        assert hygiene_check("水" * 2001).passed is False

    def test_no_text_content_rejected(self):
        assert hygiene_check("😀✨🎉").passed is False

    def test_normal_text_passes_even_short(self):
        # AI-first: normal text must reach the LLM; local rules do NOT hard-drop
        # short or keyword-less messages
        assert hygiene_check("这个周五前交一下").passed is True
        assert hygiene_check("hi").passed is True
        assert hygiene_check("好的收到").passed is True
        assert hygiene_check("哈哈哈哈").passed is True

    def test_high_certainty_homework_passes(self):
        assert hygiene_check("高数第三章作业周五晚上12点前交学习通").passed is True


class TestSignalAnalyzer:
    def test_homework_signals(self):
        r = analyze_signals("高数第三章作业周五晚上12点前交学习通")
        assert r.score >= 3.0
        assert "deadline" in r.tags
        assert "coursework" in r.tags

    def test_exam_signals(self):
        r = analyze_signals("周三下午高数考试，记得带学生证")
        assert "time" in r.tags and "affair" in r.tags

    def test_zero_score_still_analyzes(self):
        # score can be 0 — that is FINE: signals are hints, never a gate
        r = analyze_signals("这个周五前交一下")
        assert r.score >= 3.0  # time expression present
        r2 = analyze_signals("老师说还是按之前那个时间")
        assert r2.score > 0  # authority signal

    def test_signal_never_gates(self):
        # AI-first invariant: no threshold exists to block LLM access
        from campuscue.tasks.prefilter import hygiene_check

        for text in ["这个周五前交一下", "下周一上课的时候带过来", "报名表今晚就关了"]:
            assert hygiene_check(text).passed is True  # reaches LLM


# ------------------------------------------------------------------ Source Policy

class TestSourcePolicy:
    @pytest.mark.asyncio
    async def test_unconfigured_source_dropped(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.tasks.source_policy import SourcePolicy

        policy = SourcePolicy(SourceRepository(db_raw.session))
        result = await policy.evaluate(_group_event(text="高数作业周五交"))
        assert result.allowed is False
        assert result.reason == "source_not_configured"

    @pytest.mark.asyncio
    async def test_disabled_source_dropped(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.tasks.source_policy import SourcePolicy

        repo = SourceRepository(db_raw.session)
        await repo.create(platform="onebot", conversation_id="g1", enabled=False)
        policy = SourcePolicy(repo)
        result = await policy.evaluate(_group_event(conversation="g1"))
        assert result.allowed is False
        assert result.reason == "source_disabled"

    @pytest.mark.asyncio
    async def test_auto_extract_disabled(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.tasks.source_policy import SourcePolicy

        repo = SourceRepository(db_raw.session)
        await repo.create(platform="onebot", conversation_id="g1", auto_extract=False)
        policy = SourcePolicy(repo)
        result = await policy.evaluate(_group_event(conversation="g1"))
        assert result.allowed is False
        assert result.reason == "auto_extract_disabled"

    @pytest.mark.asyncio
    async def test_enabled_source_passes(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.tasks.source_policy import SourcePolicy

        repo = SourceRepository(db_raw.session)
        await repo.create(platform="onebot", conversation_id="g1")
        policy = SourcePolicy(repo)
        result = await policy.evaluate(_group_event(conversation="g1"))
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_private_message_unsupported(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository
        from campuscue.tasks.source_policy import SourcePolicy

        repo = SourceRepository(db_raw.session)
        await repo.create(platform="onebot", conversation_id="u1")
        policy = SourcePolicy(repo)
        result = await policy.evaluate(_private_event())
        assert result.allowed is False
        assert result.reason == "unsupported_conversation_type"


# ------------------------------------------------------------------ Time Normalizer

class TestTimeNormalizer:
    def test_friday_night_12(self):
        # "周五晚上12点前" anchored Monday 2026-08-10 -> Friday 2026-08-14 23:59 +08:00
        r = resolve_deadline("周五晚上12点前", ANCHOR, TZ)
        assert r.deadline is not None
        assert r.deadline == datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)  # 23:59+08 = 15:59 UTC

    def test_today_night(self):
        r = resolve_deadline("今晚", ANCHOR, TZ)
        assert r.deadline == datetime(2026, 8, 10, 15, 59, tzinfo=timezone.utc)  # 23:59+08

    def test_tomorrow_morning(self):
        r = resolve_deadline("明早", ANCHOR, TZ)
        assert r.deadline == datetime(2026, 8, 11, 0, 0, tzinfo=timezone.utc)  # 08:00+08

    def test_bare_date(self):
        r = resolve_deadline("8月14日截止", ANCHOR, TZ)
        assert r.deadline == datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        assert r.is_explicit is True

    def test_cross_year(self):
        anchor = datetime(2026, 12, 20, 0, 0, tzinfo=TZ)
        r = resolve_deadline("1月5日", anchor, TZ)
        assert r.deadline is not None
        assert r.deadline.year == 2027

    def test_past_rejected(self):
        # 前天 from 00:00 anchor is ~24h in the past, beyond the 2h tolerance
        r = resolve_deadline("前天交", ANCHOR, TZ)
        assert r.deadline is None  # past rejected

    def test_future_400d_rejected(self):
        r = resolve_deadline("2027年12月1日", ANCHOR, TZ)
        assert r.deadline is None  # > 400 days

    def test_unknown_phrase(self):
        r = resolve_deadline("期末考试前", ANCHOR, TZ)
        assert r.deadline is None
        assert r.reason == "unresolved"


# ------------------------------------------------------------------ Dedup

class TestDedup:
    @pytest.mark.asyncio
    async def test_same_source_message_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        await tasks.create(title="作业", source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=src.id, source_message_id="m1", title="作业", course=None, deadline=None)
        assert r.is_duplicate and r.reason == "same_source_message"

    @pytest.mark.asyncio
    async def test_same_semantic_36h_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="第三章作业", course="高等数学", deadline=deadline,
                           source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=src.id, source_message_id="m2", title="第三章作业",
                              course="高等数学", deadline=deadline)
        assert r.is_duplicate and r.reason == "same_semantic_task"

    @pytest.mark.asyncio
    async def test_same_key_different_source_not_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        s1 = await sources.create(platform="onebot", conversation_id="g1")
        s2 = await sources.create(platform="onebot", conversation_id="g2")
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="第三章作业", deadline=deadline, source_id=s1.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=s2.id, source_message_id="m2", title="第三章作业",
                              course=None, deadline=deadline)
        assert r.is_duplicate is False  # different source scope

    @pytest.mark.asyncio
    async def test_same_key_over_36h_not_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session, clock=clock)
        src = await sources.create(platform="onebot", conversation_id="g1")
        deadline = datetime(2026, 8, 20, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="第三章作业", deadline=deadline, source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        clock.advance(37 * 3600)  # > 36h later
        r = await dedup.check(source_id=src.id, source_message_id="m2", title="第三章作业",
                              course=None, deadline=deadline)
        assert r.is_duplicate is False

    @pytest.mark.asyncio
    async def test_dismissed_recent_still_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.storage.enums import TaskStatus
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="作业", deadline=deadline, status=TaskStatus.DISMISSED.value,
                           source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=src.id, source_message_id="m2", title="作业", course=None, deadline=deadline)
        assert r.is_duplicate is True

    @pytest.mark.asyncio
    async def test_punctuation_normalized_title_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator, normalize_title

        assert normalize_title("提交 实验三 报告！") == normalize_title("提交实验三报告")
        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="提交 实验三 报告！", deadline=deadline, source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=src.id, source_message_id="m2", title="提交实验三报告",
                              course=None, deadline=deadline)
        assert r.is_duplicate is True

    @pytest.mark.asyncio
    async def test_different_deadline_not_duplicate(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.dedup import Deduplicator

        clock = FixedClock()
        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        d1 = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        d2 = datetime(2026, 8, 21, 15, 59, tzinfo=timezone.utc)
        await tasks.create(title="作业", deadline=d1, source_id=src.id, source_message_id="m1")
        dedup = Deduplicator(tasks, clock=clock)
        r = await dedup.check(source_id=src.id, source_message_id="m2", title="作业", course=None, deadline=d2)
        assert r.is_duplicate is False


# ------------------------------------------------------------------ Extractor

class TestExtractor:
    def _provider(self, handler):
        from campuscue.providers.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            base_url="https://x/v1", model="m",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    def _resp(self, content):
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}], "usage": {}})

    @pytest.mark.asyncio
    async def test_valid_json_schema_response(self):
        from campuscue.tasks.extractor import TaskExtractor

        calls = []

        def handler(request):
            calls.append(request)
            body = json.loads(request.content)
            assert body["response_format"]["type"] == "json_schema"  # schema contract used
            return self._resp(json.dumps({"has_task": True, "category": "homework", "title": "第三章作业",
                                          "course": "高等数学", "deadline_phrase": "周五晚上12点前",
                                          "submission_method": "学习通", "confidence": 0.9, "reason": "明确截止"}))

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="高数作业周五交", context_lines=[], message_time_iso="2026-08-10T00:00:00+08:00")
        assert result.has_task and result.task.title == "第三章作业"
        assert len(calls) == 1  # no fallback

    @pytest.mark.asyncio
    async def test_has_task_false(self):
        from campuscue.tasks.extractor import TaskExtractor

        def handler(request):
            return self._resp(json.dumps({"has_task": False}))

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="晚上好", context_lines=[], message_time_iso="x")
        assert result.has_task is False

    @pytest.mark.asyncio
    async def test_fenced_json(self):
        from campuscue.tasks.extractor import TaskExtractor

        def handler(request):
            return self._resp("```json\n" + json.dumps({"has_task": True, "title": "作业A"}) + "\n```")

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert result.task.title == "作业A"

    @pytest.mark.asyncio
    async def test_padded_json(self):
        from campuscue.tasks.extractor import TaskExtractor

        def handler(request):
            return self._resp("好的，这是结果：" + json.dumps({"has_task": True, "title": "作业B"}) + "，请查收")

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert result.task.title == "作业B"

    @pytest.mark.asyncio
    async def test_invalid_json_raises(self):
        from campuscue.tasks.extractor import ExtractionError, TaskExtractor

        def handler(request):
            return self._resp("完全不是 JSON")

        ex = TaskExtractor(self._provider(handler))
        with pytest.raises(ExtractionError):
            await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")

    @pytest.mark.asyncio
    async def test_confidence_95_coerced(self):
        from campuscue.tasks.extractor import TaskExtractor

        def handler(request):
            return self._resp(json.dumps({"has_task": True, "title": "作业", "confidence": 95}))

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert result.task.confidence == 0.95

    @pytest.mark.asyncio
    async def test_invalid_category_to_other(self):
        from campuscue.tasks.extractor import TaskExtractor

        def handler(request):
            return self._resp(json.dumps({"has_task": True, "title": "作业", "category": "banana"}))

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert result.task.category == "other"

    @pytest.mark.asyncio
    async def test_missing_title_raises(self):
        from campuscue.tasks.extractor import ExtractionError, TaskExtractor

        def handler(request):
            return self._resp(json.dumps({"has_task": True, "course": "数学"}))

        ex = TaskExtractor(self._provider(handler))
        with pytest.raises(ExtractionError, match="title"):
            await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")

    @pytest.mark.asyncio
    async def test_schema_invalid_request_fallback_once(self):
        from campuscue.providers.errors import ProviderError, ProviderErrorCode
        from campuscue.tasks.extractor import TaskExtractor

        calls = []

        def handler(request):
            calls.append(json.loads(request.content))
            if len(calls) == 1:
                raise ProviderError(ProviderErrorCode.INVALID_REQUEST, "json_schema unsupported")
            return self._resp(json.dumps({"has_task": True, "title": "作业F"}))

        ex = TaskExtractor(self._provider(handler))
        result = await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert result.task.title == "作业F"
        assert result.structured_mode == "json_fallback"
        assert len(calls) == 2  # exactly one fallback
        assert "response_format" not in calls[1]  # fallback has no schema

    @pytest.mark.asyncio
    async def test_auth_error_no_fallback(self):
        from campuscue.providers.errors import ProviderError, ProviderErrorCode
        from campuscue.tasks.extractor import TaskExtractor

        calls = []

        def handler(request):
            calls.append(1)
            raise ProviderError(ProviderErrorCode.AUTH_ERROR, "bad key")

        ex = TaskExtractor(self._provider(handler))
        with pytest.raises(ProviderError) as ei:
            await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR
        assert len(calls) == 1  # NO fallback

    @pytest.mark.asyncio
    async def test_timeout_no_fallback(self):
        from campuscue.providers.errors import ProviderError, ProviderErrorCode
        from campuscue.tasks.extractor import TaskExtractor

        calls = []

        def handler(request):
            calls.append(1)
            raise ProviderError(ProviderErrorCode.TIMEOUT, "timeout")

        ex = TaskExtractor(self._provider(handler))
        with pytest.raises(ProviderError):
            await ex.extract(current_text="作业", context_lines=[], message_time_iso="x")
        assert len(calls) == 1


# ------------------------------------------------------------------ Task Service

class TestTaskService:
    @pytest.mark.asyncio
    async def test_normal_task_pending(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.services.task_service import TaskService
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.models import TaskCandidate

        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        service = TaskService(tasks, clock=FixedClock())
        candidate = TaskCandidate(
            title="作业", category="homework", course=None,
            deadline=datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc),
            description=None, confidence=0.9, dedup_key="k1",
            source_id=src.id, source_message_id="m1", source_text_reference="原文",
            pending_confirm=False,
        )
        result = await service.create_task(candidate)
        assert result.created and result.task.status == "pending"
        assert result.task.source_text_reference == "原文"

    @pytest.mark.asyncio
    async def test_low_confidence_pending_confirm(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.services.task_service import TaskService, decide_pending_confirm
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.models import TaskCandidate

        assert decide_pending_confirm(confidence=0.4, deadline=object(), deadline_resolved=True) is True

        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        service = TaskService(tasks, clock=FixedClock())
        candidate = TaskCandidate(
            title="作业", category="other", course=None, deadline=None,
            description=None, confidence=0.4, dedup_key="k2",
            source_id=src.id, source_message_id="m2", source_text_reference="原文",
            pending_confirm=True,
        )
        result = await service.create_task(candidate)
        assert result.created and result.task.status == "pending_confirm"

    @pytest.mark.asyncio
    async def test_unresolved_deadline_pending_confirm(self, db_raw):
        from campuscue.services.task_service import decide_pending_confirm

        assert decide_pending_confirm(confidence=0.9, deadline="某物", deadline_resolved=False) is True

    @pytest.mark.asyncio
    async def test_duplicate_returns_not_created(self, db_raw):
        from campuscue.repositories.repositories import SourceRepository, TaskRepository
        from campuscue.services.task_service import TaskService
        from campuscue.storage.clock import FixedClock
        from campuscue.tasks.models import TaskCandidate

        sources = SourceRepository(db_raw.session)
        tasks = TaskRepository(db_raw.session)
        src = await sources.create(platform="onebot", conversation_id="g1")
        service = TaskService(tasks, clock=FixedClock())
        base = dict(
            title="作业", category="homework", course=None,
            deadline=datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc),
            description=None, confidence=0.9, dedup_key="k",
            source_id=src.id, source_text_reference="原文", pending_confirm=False,
        )
        r1 = await service.create_task(TaskCandidate(**base, source_message_id="m1"))
        assert r1.created
        r2 = await service.create_task(TaskCandidate(**base, source_message_id="m2"))
        assert r2.created is False  # same semantic task duplicate
        assert r2.reason == "same_semantic_task"


# ------------------------------------------------------------------ helpers

def _group_event(*, conversation="g1", text="高数作业周五交"):
    from campuscue.core.events import CampusEvent, ConversationType, EventType

    return CampusEvent(
        event_id="e1", trace_id="t1", platform="onebot", adapter_id="a",
        event_type=EventType.GROUP_MESSAGE, self_id="10001", message_id="m1",
        conversation_id=conversation, conversation_type=ConversationType.GROUP,
        sender_id="5", sender_name="", text=text,
        timestamp=datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc),
    )


def _private_event():
    from campuscue.core.events import CampusEvent, ConversationType, EventType

    return CampusEvent(
        event_id="e2", trace_id="t2", platform="onebot", adapter_id="a",
        event_type=EventType.PRIVATE_MESSAGE, self_id="10001", message_id="m2",
        conversation_id="u1", conversation_type=ConversationType.PRIVATE,
        sender_id="5", sender_name="", text="高数作业周五交",
        timestamp=datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc),
    )
