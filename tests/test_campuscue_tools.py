"""The five tools, against a real database.

These run on a temporary SQLite file rather than with mocked store functions,
because most of what can go wrong here is at the boundary: an aware datetime
bound against a naive column, a dedup key that does not match, a status filter
that quietly excludes pending_confirm. Mocking the store would assert that the
tools call it, which is not the property that matters.

The scheduler is deliberately left unbound. ``schedule_for_task`` degrades to a
no-op without a cron manager (campuscue/reminders.py), so these tests exercise the
tools' own behaviour and the reminder timing stays tested in
test_campuscue_reminders.py where it can be pinned to a fixed clock.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import store
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import CampusTask
from campuscue.tools import (
    CampusAnalyzeOpportunityTool,
    CampusCompleteTaskTool,
    CampusCreateTaskTool,
    CampusListTasksTool,
    CampusSetReminderTool,
    build_tools,
)

UMO = "aiocqhttp:GroupMessage:tools-test"
OTHER_UMO = "aiocqhttp:GroupMessage:someone-else"


class FakeEvent:
    def __init__(self, umo: str = UMO) -> None:
        self.unified_msg_origin = umo


class FakeAgentContext:
    def __init__(self, umo: str = UMO) -> None:
        self.event = FakeEvent(umo)


class FakeWrapper:
    """Stands in for ContextWrapper[AstrAgentContext].

    The tools only reach ``context.context.event.unified_msg_origin``; building a
    real wrapper would need a live Context and an AstrMessageEvent, neither of
    which changes what is being tested.
    """

    def __init__(self, umo: str = UMO) -> None:
        self.context = FakeAgentContext(umo)


@pytest.fixture
def ctx() -> FakeWrapper:
    return FakeWrapper()


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    """A throwaway SQLite file, wired in where the store looks for it.

    ``campuscue.store`` binds astrbot's global ``db_helper`` at import time, so the
    patch has to target the store's own attribute rather than
    ``astrbot.core.db_helper``. ``reminders`` reaches the database through
    ``store.db_helper``, so it follows automatically.
    """
    db = SQLiteDatabase(str(tmp_path / "campus-tools-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    try:
        yield db
    finally:
        await db.engine.dispose()


async def make_task(**kw) -> CampusTask:
    defaults = {
        "umo": UMO,
        "title": "已有任务",
        "task_type": "homework",
        "status": "active",
        "deadline": datetime.now(timezone.utc) + timedelta(days=3),
    }
    defaults.update(kw)
    task = CampusTask(**defaults)
    task.dedup_key = store.dedup_key(task.umo, task.title, task.deadline)
    return await store.create_task(task)


# --- create ---------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_it_creates_a_task_with_an_absolute_deadline(self, ctx, campus_db):
        out = await CampusCreateTaskTool().call(
            ctx,
            title="提交软件工程实验三报告",
            task_type="homework",
            deadline="2026-12-14T23:59:00+08:00",
        )
        assert "已创建" in out
        tasks = await store.list_tasks(UMO)
        assert [t.title for t in tasks] == ["提交软件工程实验三报告"]
        assert tasks[0].source_kind == "manual"

    @pytest.mark.asyncio
    async def test_a_naive_deadline_is_read_as_campus_time(self, ctx, campus_db):
        """The model echoes what the student said out loud, and they meant their
        own clock. Reading it as UTC would shift every deadline 8 hours."""
        await CampusCreateTaskTool().call(
            ctx, title="交实验", deadline="2026-12-14 23:59"
        )
        task = (await store.list_tasks(UMO))[0]
        local = task.deadline.replace(tzinfo=timezone.utc).astimezone(CAMPUS_TZ)
        assert (local.hour, local.minute) == (23, 59)
        assert local.day == 14

    @pytest.mark.asyncio
    async def test_a_missing_title_is_an_error_not_an_empty_task(self, ctx, campus_db):
        out = await CampusCreateTaskTool().call(ctx, title="   ")
        assert out.startswith("error:")
        assert await store.list_tasks(UMO) == []

    @pytest.mark.asyncio
    async def test_an_unparseable_deadline_is_reported_not_silently_dropped(
        self, ctx, campus_db
    ):
        """Dropping it would produce an undated task the student believes has a
        deadline -- worse than refusing."""
        out = await CampusCreateTaskTool().call(
            ctx, title="交实验", deadline="下周五晚上"
        )
        assert out.startswith("error:")
        assert await store.list_tasks(UMO) == []

    @pytest.mark.asyncio
    async def test_dictating_a_task_that_already_exists_does_not_duplicate_it(
        self, ctx, campus_db
    ):
        """ "帮我记一下老师刚发的作业" for something the pipeline already extracted
        must not produce two sets of reminders for one obligation."""
        await CampusCreateTaskTool().call(
            ctx, title="交实验三", deadline="2026-12-14T23:59:00+08:00"
        )
        out = await CampusCreateTaskTool().call(
            ctx, title="交实验三", deadline="2026-12-14T23:59:00+08:00"
        )
        assert "已存在" in out
        assert len(await store.list_tasks(UMO)) == 1

    @pytest.mark.asyncio
    async def test_an_unknown_task_type_falls_back_rather_than_failing(
        self, ctx, campus_db
    ):
        await CampusCreateTaskTool().call(
            ctx,
            title="某事",
            task_type="迷惑类型",
            deadline="2026-12-14T12:00:00+08:00",
        )
        assert (await store.list_tasks(UMO))[0].task_type == "notice"

    @pytest.mark.asyncio
    async def test_an_undated_task_is_accepted(self, ctx, campus_db):
        """ "下周交，时间待通知" is real information; refusing it would lose it."""
        out = await CampusCreateTaskTool().call(ctx, title="待通知的作业")
        assert "已创建" in out
        task = (await store.list_tasks(UMO))[0]
        assert task.deadline is None
        assert task.deadline_is_explicit is False


# --- list -----------------------------------------------------------------


class TestList:
    @pytest.mark.asyncio
    async def test_an_empty_board_says_so_instead_of_returning_nothing(
        self, ctx, campus_db
    ):
        out = await CampusListTasksTool().call(ctx)
        assert "没有" in out

    @pytest.mark.asyncio
    async def test_open_includes_tasks_awaiting_confirmation(self, ctx, campus_db):
        """A pending_confirm task has a real deadline. Hiding it from "我还有什么没交"
        is how a student misses it."""
        await make_task(title="确定的作业")
        await make_task(title="待确认的作业", status="pending_confirm")
        out = await CampusListTasksTool().call(ctx, scope="open")
        assert "确定的作业" in out
        assert "待确认的作业" in out
        assert "待确认" in out

    @pytest.mark.asyncio
    async def test_done_tasks_are_not_in_the_open_list(self, ctx, campus_db):
        await make_task(title="交了的作业", status="done")
        out = await CampusListTasksTool().call(ctx, scope="open")
        assert "交了的作业" not in out

    @pytest.mark.asyncio
    async def test_overdue_selects_only_past_deadlines(self, ctx, campus_db):
        await make_task(
            title="逾期的", deadline=datetime.now(timezone.utc) - timedelta(days=1)
        )
        await make_task(title="没到期的")
        out = await CampusListTasksTool().call(ctx, scope="overdue")
        assert "逾期的" in out
        assert "没到期的" not in out
        assert "已逾期" in out

    @pytest.mark.asyncio
    async def test_week_excludes_something_a_month_out(self, ctx, campus_db):
        await make_task(title="本周的")
        await make_task(
            title="下个月的", deadline=datetime.now(timezone.utc) + timedelta(days=30)
        )
        out = await CampusListTasksTool().call(ctx, scope="week")
        assert "本周的" in out
        assert "下个月的" not in out

    @pytest.mark.asyncio
    async def test_undated_tasks_do_not_appear_in_time_bounded_scopes(
        self, ctx, campus_db
    ):
        """A task with no deadline cannot be due today; including it would put a
        false urgency on the one item nobody can act on yet."""
        await make_task(title="无期限的", deadline=None)
        out = await CampusListTasksTool().call(ctx, scope="today")
        assert "无期限的" not in out

    @pytest.mark.asyncio
    async def test_the_type_filter_narrows_the_list(self, ctx, campus_db):
        await make_task(title="一次作业", task_type="homework")
        await make_task(title="一场考试", task_type="exam")
        out = await CampusListTasksTool().call(ctx, task_type="exam")
        assert "一场考试" in out
        assert "一次作业" not in out

    @pytest.mark.asyncio
    async def test_another_groups_tasks_are_invisible(self, ctx, campus_db):
        await make_task(title="别人的作业", umo=OTHER_UMO)
        out = await CampusListTasksTool().call(ctx)
        assert "别人的作业" not in out

    @pytest.mark.asyncio
    async def test_the_remaining_phrase_is_precomputed(self, ctx, campus_db):
        """The model must never have to subtract two dates."""
        await make_task(
            deadline=datetime.now(timezone.utc) + timedelta(days=3, hours=1)
        )
        out = await CampusListTasksTool().call(ctx)
        assert "还剩 3 天" in out

    @pytest.mark.asyncio
    async def test_a_long_list_is_capped(self, ctx, campus_db):
        from campuscue.tools import MAX_LISTED

        for i in range(MAX_LISTED + 5):
            await make_task(title=f"作业{i}")
        out = await CampusListTasksTool().call(ctx)
        assert f"共 {MAX_LISTED + 5} 条" in out
        assert len(out.strip().split("\n")) == MAX_LISTED + 1


# --- complete -------------------------------------------------------------


class TestComplete:
    @pytest.mark.asyncio
    async def test_it_completes_by_id_prefix(self, ctx, campus_db):
        """Listings show a truncated id, and the model hands back what it saw."""
        task = await make_task(title="要交的作业")
        out = await CampusCompleteTaskTool().call(ctx, task=task.task_id[:8])
        assert "已完成" in out
        assert (await store.get_task(task.task_id)).status == "done"

    @pytest.mark.asyncio
    async def test_it_completes_by_exact_title(self, ctx, campus_db):
        task = await make_task(title="要交的作业")
        await CampusCompleteTaskTool().call(ctx, task="要交的作业")
        assert (await store.get_task(task.task_id)).status == "done"

    @pytest.mark.asyncio
    async def test_an_ambiguous_title_changes_nothing(self, ctx, campus_db):
        """Two tasks share a title. Completing "one of them" would be a coin flip
        on the student's behalf, so nothing happens and the model is told to ask."""
        a = await make_task(title="重名的作业")
        b = await make_task(
            title="重名的作业", deadline=datetime.now(timezone.utc) + timedelta(days=9)
        )
        out = await CampusCompleteTaskTool().call(ctx, task="重名的作业")
        assert out.startswith("error:")
        assert (await store.get_task(a.task_id)).status == "active"
        assert (await store.get_task(b.task_id)).status == "active"

    @pytest.mark.asyncio
    async def test_a_task_from_another_group_cannot_be_completed(self, ctx, campus_db):
        task = await make_task(title="别人的作业", umo=OTHER_UMO)
        out = await CampusCompleteTaskTool().call(ctx, task=task.task_id)
        assert out.startswith("error:")
        assert (await store.get_task(task.task_id)).status == "active"

    @pytest.mark.asyncio
    async def test_dismiss_marks_dismissed_not_done(self, ctx, campus_db):
        """The distinction is the false-positive rate: "I did it" and "that was
        never a task" say opposite things about the extractor."""
        task = await make_task()
        await CampusCompleteTaskTool().call(ctx, task=task.task_id, action="dismiss")
        assert (await store.get_task(task.task_id)).status == "dismissed"

    @pytest.mark.asyncio
    async def test_reopen_restores_a_completed_task(self, ctx, campus_db):
        task = await make_task(status="done")
        out = await CampusCompleteTaskTool().call(
            ctx, task=task.task_id, action="reopen"
        )
        assert "已恢复" in out
        assert (await store.get_task(task.task_id)).status == "active"

    @pytest.mark.asyncio
    async def test_completing_something_already_done_is_reported_not_repeated(
        self, ctx, campus_db
    ):
        task = await make_task(status="done")
        out = await CampusCompleteTaskTool().call(ctx, task=task.task_id)
        assert "无需重复" in out


# --- set_reminder ---------------------------------------------------------


class TestSetReminder:
    @pytest.mark.asyncio
    async def test_moving_the_deadline_updates_the_task(self, ctx, campus_db):
        task = await make_task()
        out = await CampusSetReminderTool().call(
            ctx, task=task.task_id, deadline="2026-12-20T18:00:00+08:00"
        )
        assert "12-20 18:00" in out
        fresh = await store.get_task(task.task_id)
        local = fresh.deadline.replace(tzinfo=timezone.utc).astimezone(CAMPUS_TZ)
        assert (local.month, local.day, local.hour) == (12, 20, 18)

    @pytest.mark.asyncio
    async def test_a_corrected_deadline_is_marked_explicit(self, ctx, campus_db):
        """A human typed it, so the "AI guessed this time" badge must come off."""
        task = await make_task(deadline_is_explicit=False)
        await CampusSetReminderTool().call(
            ctx, task=task.task_id, deadline="2026-12-20T18:00:00+08:00"
        )
        assert (await store.get_task(task.task_id)).deadline_is_explicit is True

    @pytest.mark.asyncio
    async def test_the_dedup_key_follows_a_corrected_deadline(self, ctx, campus_db):
        """Otherwise the original notice re-extracts straight back into the task
        the student just fixed."""
        task = await make_task()
        before = task.dedup_key
        await CampusSetReminderTool().call(
            ctx, task=task.task_id, deadline="2026-12-20T18:00:00+08:00"
        )
        assert (await store.get_task(task.task_id)).dedup_key != before

    @pytest.mark.asyncio
    async def test_an_undated_task_cannot_have_reminders(self, ctx, campus_db):
        task = await make_task(deadline=None)
        out = await CampusSetReminderTool().call(ctx, task=task.task_id)
        assert out.startswith("error:")
        assert "截止时间" in out

    @pytest.mark.asyncio
    async def test_a_completed_task_is_refused(self, ctx, campus_db):
        task = await make_task(status="done")
        out = await CampusSetReminderTool().call(ctx, task=task.task_id)
        assert out.startswith("error:")

    @pytest.mark.asyncio
    async def test_nonsense_lead_minutes_are_refused_not_clamped(self, ctx, campus_db):
        """A model that passes 999999 meant something else. Clamping would give a
        confident answer to a request nobody made."""
        task = await make_task()
        out = await CampusSetReminderTool().call(
            ctx, task=task.task_id, lead_minutes=[99999999]
        )
        assert out.startswith("error:")


# --- analyze_opportunity --------------------------------------------------


class TestAnalyze:
    @pytest.mark.asyncio
    async def test_it_reports_the_real_conflicts_from_the_database(
        self, ctx, campus_db
    ):
        deadline = datetime.now(timezone.utc) + timedelta(days=5)
        await make_task(title="窗口内的作业", deadline=deadline - timedelta(days=1))
        out = await CampusAnalyzeOpportunityTool().call(
            ctx,
            title="数学建模竞赛",
            deadline=deadline.isoformat(),
            effort_days=3,
        )
        assert "窗口内的作业" in out
        assert "还有 1 件事" in out

    @pytest.mark.asyncio
    async def test_tasks_outside_the_work_window_are_not_conflicts(
        self, ctx, campus_db
    ):
        """Something due tomorrow does not compete with a competition three
        months out -- it will be long finished."""
        deadline = datetime.now(timezone.utc) + timedelta(days=90)
        await make_task(
            title="明天的作业", deadline=datetime.now(timezone.utc) + timedelta(days=1)
        )
        out = await CampusAnalyzeOpportunityTool().call(
            ctx, title="很远的比赛", deadline=deadline.isoformat(), effort_days=3
        )
        assert "明天的作业" not in out
        assert "没有其它到期任务" in out

    @pytest.mark.asyncio
    async def test_not_enough_time_is_flagged_arithmetically(self, ctx, campus_db):
        deadline = datetime.now(timezone.utc) + timedelta(days=2)
        out = await CampusAnalyzeOpportunityTool().call(
            ctx, title="来不及的比赛", deadline=deadline.isoformat(), effort_days=10
        )
        assert "时间不足" in out

    @pytest.mark.asyncio
    async def test_exams_in_the_window_are_called_out_separately(self, ctx, campus_db):
        deadline = datetime.now(timezone.utc) + timedelta(days=4)
        await make_task(
            title="数据结构期末",
            task_type="exam",
            deadline=deadline - timedelta(days=1),
        )
        out = await CampusAnalyzeOpportunityTool().call(
            ctx, title="某比赛", deadline=deadline.isoformat(), effort_days=5
        )
        assert "场考试" in out
        assert "数据结构期末" in out

    @pytest.mark.asyncio
    async def test_a_past_opportunity_is_an_error(self, ctx, campus_db):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        out = await CampusAnalyzeOpportunityTool().call(
            ctx, title="错过的比赛", deadline=past.isoformat()
        )
        assert out.startswith("error:")

    @pytest.mark.asyncio
    async def test_it_states_load_but_not_a_verdict(self, ctx, campus_db):
        """The tool supplies numbers; the model advises. A hard-coded 建议参加
        would be a database query pretending to be judgement."""
        deadline = datetime.now(timezone.utc) + timedelta(days=5)
        out = await CampusAnalyzeOpportunityTool().call(
            ctx, title="某比赛", deadline=deadline.isoformat()
        )
        assert "负载" in out
        assert "建议" not in out


# --- registration ---------------------------------------------------------


def test_all_five_tools_have_valid_schemas_and_unique_names():
    """FunctionTool validates ``parameters`` against the JSON Schema metaschema at
    construction, so instantiating is the check."""
    tools = build_tools()
    assert len(tools) == 5
    names = [t.name for t in tools]
    assert len(set(names)) == 5
    assert all(name.startswith("campus_") for name in names)
    for tool in tools:
        assert tool.description
        assert tool.parameters["type"] == "object"
