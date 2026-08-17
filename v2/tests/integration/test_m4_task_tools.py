"""M4 task tools + source isolation tests (test matrix 16-29).

Production paths: real temp SQLite + TaskRepository + TaskService +
ReminderService + ToolRegistry + real tools. Source isolation is enforced at
the SERVICE/TOOL boundary — a hallucinated foreign task id must never reveal
cross-source existence.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.core.events import ConversationType
from campuscue.storage.clock import FixedClock
from campuscue.storage.enums import ReminderStatus, ReminderType, TaskStatus
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import ToolRegistry
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 12, 4, 0, 0, tzinfo=timezone.utc)  # 2026-08-12 12:00 +08 (Wed)


def _dl(days: int, hours: int = 0) -> datetime:
    local = NOW.astimezone(TZ) + timedelta(days=days, hours=hours)
    return local.astimezone(timezone.utc)


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "m4.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
def clock():
    return FixedClock(NOW)


@pytest.fixture
async def services(db, clock):
    """Real repos/services for two sources (A and B)."""
    from campuscue.repositories.repositories import (
        ReminderRepository,
        SourceRepository,
        TaskRepository,
    )
    from campuscue.services.reminder_service import ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.tasks.reminder_policy import ReminderPolicy

    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)

    reminder_service = ReminderService(
        reminders, tasks, clock=clock, timezone=TZ,
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)

    a = await sources.create(
        platform="onebot", conversation_id="gA", name="A",
        enabled=True, auto_extract=True, context_window=5,
        privacy_policy="default",
    )
    b = await sources.create(
        platform="onebot", conversation_id="gB", name="B",
        enabled=True, auto_extract=True, context_window=5,
        privacy_policy="default",
    )
    return {
        "sources": sources, "tasks": tasks, "reminders": reminders,
        "task_service": task_service, "reminder_service": reminder_service,
        "source_a": a.id, "source_b": b.id,
    }


async def _create(services, source_id, *, title="任务", course=None, deadline=None, status="pending"):
    """Seed a task through the repository (fixture seeding is NOT the path under
    test — tools go through TaskService; see task_create tests)."""
    from campuscue.storage.enums import TaskPriority

    return await services["tasks"].create(
        title=title, course=course, deadline=deadline, status=status,
        priority=TaskPriority.NORMAL.value, confidence=1.0, dedup_key=None,
        source_id=source_id, source_message_id=None, source_text_reference=None,
    )


def _tool_context(services, *, source_id, message_id="m1", ts=NOW):
    return ToolContext(
        platform="onebot", source_id=source_id, conversation_id="gA" if source_id == services["source_a"] else "gB",
        conversation_type=ConversationType.GROUP, message_id=message_id,
        timestamp=ts, trace_id="trace1", timezone=TZ,
    )


def _registry(services, clock):
    r = ToolRegistry()
    register_task_tools(
        r, task_service=services["task_service"],
        reminder_service=services["reminder_service"], tz=TZ, clock=clock,
    )
    return r


# ----------------------------------------------------------------- 16-20: isolation

class TestSourceIsolation:
    @pytest.mark.asyncio
    async def test_16_task_visible_from_own_source(self, services, clock):
        t = await _create(services, services["source_a"], title="A的任务")
        r = _registry(services, clock)
        result = await r.execute(
            "task_get", arguments={"task_id": t.id}, context=_tool_context(services, source_id=services["source_a"])
        )
        assert result.ok is True
        assert "A的任务" in result.content

    @pytest.mark.asyncio
    async def test_17_task_invisible_from_foreign_source(self, services, clock):
        t = await _create(services, services["source_b"], title="B的秘密任务")
        r = _registry(services, clock)
        result = await r.execute(
            "task_get", arguments={"task_id": t.id}, context=_tool_context(services, source_id=services["source_a"])
        )
        assert result.ok is False
        assert result.error == "task_not_found"
        assert "B的秘密任务" not in result.content  # no existence leak

    @pytest.mark.asyncio
    async def test_18_foreign_task_get_leaks_nothing(self, services, clock):
        """A GET on a foreign task must be indistinguishable from a missing id."""
        foreign = await _create(services, services["source_b"], title="B的任务")
        missing = 99999
        r = _registry(services, clock)
        ctx = _tool_context(services, source_id=services["source_a"])
        r1 = await r.execute("task_get", arguments={"task_id": foreign.id}, context=ctx)
        r2 = await r.execute("task_get", arguments={"task_id": missing}, context=ctx)
        assert r1.error == r2.error == "task_not_found"

    @pytest.mark.asyncio
    async def test_19_foreign_task_update_makes_no_mutation(self, services, clock):
        foreign = await _create(services, services["source_b"], title="B任务", course="B课")
        r = _registry(services, clock)
        result = await r.execute(
            "task_update",
            arguments={"task_id": foreign.id, "title": "被篡改"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is False
        assert result.error == "task_not_found"
        fresh = await services["tasks"].get(foreign.id)
        assert fresh.title == "B任务"
        assert fresh.course == "B课"

    @pytest.mark.asyncio
    async def test_20_foreign_complete_dismiss_make_no_mutation(self, services, clock):
        foreign = await _create(services, services["source_b"], title="B任务")
        r = _registry(services, clock)
        ctx = _tool_context(services, source_id=services["source_a"])
        c = await r.execute("task_complete", arguments={"task_id": foreign.id}, context=ctx)
        d = await r.execute("task_dismiss", arguments={"task_id": foreign.id}, context=ctx)
        assert c.ok is False and c.error == "task_not_found"
        assert d.ok is False and d.error == "task_not_found"
        fresh = await services["tasks"].get(foreign.id)
        assert fresh.status == TaskStatus.PENDING.value  # untouched


# ----------------------------------------------------------------- 21-29: task tools

class TestTaskListScopes:
    @pytest.mark.asyncio
    async def test_21_scopes(self, services, clock):
        sid = services["source_a"]
        await _create(services, sid, title="已过期", deadline=NOW - timedelta(hours=5))
        await _create(services, sid, title="今天截止", deadline=_dl(0, 6))  # today 18:00 +08
        await _create(services, sid, title="明天截止", deadline=_dl(1, 0))
        await _create(services, sid, title="下周", deadline=_dl(8, 0))
        await _create(services, sid, title="已完成", deadline=_dl(1, 0), status="done")
        await _create(services, sid, title="无截止")
        r = _registry(services, clock)
        ctx = _tool_context(services, source_id=sid)

        async def titles(scope):
            res = await r.execute("task_list", arguments={"scope": scope}, context=ctx)
            assert res.ok is True
            return [ln for ln in res.content.splitlines() if ln.startswith("-")]

        open_lines = await titles("open")
        assert len(open_lines) == 5  # 6 tasks minus done
        done = await titles("done")
        assert any("已完成" in ln for ln in done)
        overdue = await titles("overdue")
        assert any("已过期" in ln for ln in overdue)
        today = await titles("today")
        assert any("今天截止" in ln for ln in today)
        assert not any("明天截止" in ln for ln in today)
        week = await titles("week")
        assert any("明天截止" in ln for ln in week)
        assert not any("下周" in ln for ln in week)  # day 8 > 7
        pending = await titles("pending")
        assert not any("已完成" in ln for ln in pending)

    @pytest.mark.asyncio
    async def test_21b_invalid_scope_safe_failure(self, services, clock):
        r = _registry(services, clock)
        result = await r.execute(
            "task_list", arguments={"scope": "nonsense"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_22_task_get_fields(self, services, clock):
        t = await _create(
            services, services["source_a"], title="数第三章作业", course="高等数学",
            deadline=_dl(2, 0),
        )
        r = _registry(services, clock)
        result = await r.execute(
            "task_get", arguments={"task_id": t.id},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        assert "数第三章作业" in result.content
        assert "高等数学" in result.content
        assert "2026-08-14" in result.content  # local tz deadline
        assert "pending" in result.content


class TestTaskCreate:
    @pytest.mark.asyncio
    async def test_23_create_goes_through_task_service(self, services, clock):
        """tool -> TaskService -> real DB (task row exists with trusted source
        scope from context, not from model args)."""
        r = _registry(services, clock)
        ctx = _tool_context(services, source_id=services["source_a"], message_id="m-create")
        result = await r.execute(
            "task_create",
            arguments={"title": "英语作文", "course": "大学英语", "deadline_phrase": "明天晚上12点前"},
            context=ctx,
        )
        assert result.ok is True
        task_id = result.data["task_id"]
        task = await services["tasks"].get(task_id)
        assert task.title == "英语作文"
        assert task.course == "大学英语"
        assert task.source_id == services["source_a"]
        assert task.source_message_id == "m-create"  # trusted runtime value
        # deadline resolved deterministically: 明晚 = NOW+1d 23:59 +08 -> 2026-08-13 15:59 UTC
        assert task.deadline == _dl(1, 0).replace(hour=15, minute=59)
        assert task.status == TaskStatus.PENDING.value  # explicit user task, no confirm

    @pytest.mark.asyncio
    async def test_23b_unresolvable_deadline_asks_for_clarification(self, services, clock):
        r = _registry(services, clock)
        result = await r.execute(
            "task_create",
            arguments={"title": "模糊任务", "deadline_phrase": "那天的那个时间之前"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is False
        assert "无法解析截止时间" in result.error
        # nothing created
        assert await services["tasks"].list_for_source(services["source_a"]) == []

    @pytest.mark.asyncio
    async def test_24_duplicate_create_not_created(self, services, clock):
        r = _registry(services, clock)
        ctx = _tool_context(services, source_id=services["source_a"], message_id="m-dup")
        first = await r.execute(
            "task_create",
            arguments={"title": "重复任务", "deadline_phrase": "周五晚上12点前"},
            context=ctx,
        )
        assert first.ok is True
        second = await r.execute(
            "task_create",
            arguments={"title": "重复任务", "deadline_phrase": "周五晚上12点前"},
            context=ctx,
        )
        assert second.ok is False
        assert "重复" in second.content
        assert second.data["created"] is False


class TestTaskUpdate:
    @pytest.mark.asyncio
    async def test_25_update_title_course(self, services, clock):
        t = await _create(services, services["source_a"], title="旧标题", course="旧课")
        r = _registry(services, clock)
        result = await r.execute(
            "task_update",
            arguments={"task_id": t.id, "title": "新标题", "course": "新课"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        fresh = await services["tasks"].get(t.id)
        assert fresh.title == "新标题"
        assert fresh.course == "新课"

    @pytest.mark.asyncio
    async def test_25b_no_fields_validation(self, services, clock):
        t = await _create(services, services["source_a"], title="保持")
        r = _registry(services, clock)
        result = await r.execute(
            "task_update", arguments={"task_id": t.id},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is False

    @pytest.mark.asyncio
    async def test_26_deadline_update_rebuilds_reminders(self, services, clock):
        """M3 coupling through TaskService: deadline change -> old plan
        cancelled, new plan installed (NOT a second mutation pathway)."""
        t = await _create(services, services["source_a"], title="带提醒", deadline=_dl(3, 0))
        await services["reminder_service"].plan_reminders(t)
        before = await services["reminders"].list_for_task(t.id)
        assert len(before) == 3 and all(x.status == "scheduled" for x in before)

        r = _registry(services, clock)
        result = await r.execute(
            "task_update",
            arguments={"task_id": t.id, "deadline_phrase": "明天晚上12点"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        after = await services["reminders"].list_for_task(t.id)
        active = [x for x in after if x.status == ReminderStatus.SCHEDULED.value]
        assert len(active) == 3  # day_before/hours_before/deadline all valid
        new_deadline = _dl(1, 0).replace(hour=15, minute=59)  # 明晚 23:59 +08
        assert all(x.trigger_at < new_deadline for x in active)

    @pytest.mark.asyncio
    async def test_27_complete_cancels_reminders(self, services, clock):
        t = await _create(services, services["source_a"], title="完成我", deadline=_dl(3, 0))
        await services["reminder_service"].plan_reminders(t)
        r = _registry(services, clock)
        result = await r.execute(
            "task_complete", arguments={"task_id": t.id},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        fresh = await services["tasks"].get(t.id)
        assert fresh.status == TaskStatus.DONE.value
        assert all(x.status == ReminderStatus.CANCELLED.value
                   for x in await services["reminders"].list_for_task(t.id))

    @pytest.mark.asyncio
    async def test_28_dismiss_cancels_reminders(self, services, clock):
        t = await _create(services, services["source_a"], title="忽略我", deadline=_dl(3, 0))
        await services["reminder_service"].plan_reminders(t)
        r = _registry(services, clock)
        result = await r.execute(
            "task_dismiss", arguments={"task_id": t.id},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        fresh = await services["tasks"].get(t.id)
        assert fresh.status == TaskStatus.DISMISSED.value
        assert all(x.status == ReminderStatus.CANCELLED.value
                   for x in await services["reminders"].list_for_task(t.id))


class TestReminderList:
    @pytest.mark.asyncio
    async def test_29_reminder_list_scoped(self, services, clock):
        """Only reminders of CURRENT-source tasks appear; B's reminders are
        invisible from A."""
        ta = await _create(services, services["source_a"], title="A带提醒", deadline=_dl(3, 0))
        tb = await _create(services, services["source_b"], title="B带提醒", deadline=_dl(3, 0))
        await services["reminder_service"].plan_reminders(ta)
        await services["reminder_service"].plan_reminders(tb)
        r = _registry(services, clock)
        result = await r.execute(
            "reminder_list", arguments={"status": "scheduled"},
            context=_tool_context(services, source_id=services["source_a"]),
        )
        assert result.ok is True
        assert f"#{ta.id}" in result.content
        assert f"#{tb.id}" not in result.content

    @pytest.mark.asyncio
    async def test_29b_reminder_list_not_implemented_when_reminders_disabled(self, services, clock):
        """reminder_service=None -> tool set has NO reminder_list (canonical
        M4 §17 keeps tool count small; registration is conditional)."""
        from campuscue.services.task_service import TaskService
        from campuscue.storage.clock import SystemClock

        svc = services
        r = ToolRegistry()
        register_task_tools(
            r, task_service=TaskService(svc["tasks"], clock=SystemClock()),
            reminder_service=None, tz=TZ, clock=SystemClock(),
        )
        assert r.get("reminder_list") is None
        assert all(t.name in ("task_list", "task_get", "task_create", "task_update",
                              "task_complete", "task_dismiss") for t in r.list())
