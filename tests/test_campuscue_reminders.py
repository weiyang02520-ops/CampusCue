"""Reminder timing, pinned against a fixed clock.

``plan_reminders`` is pure on purpose so that every rule about *when* a student
gets nudged can be asserted here instead of by waiting for a scheduler. The
quiet-hours cases are the ones worth having: they are the only place in the
codebase where a reminder deliberately fires at a different time than the lead
asks for, and the "slide backward when sliding forward would pass the deadline"
branch is easy to break and impossible to notice by hand.
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import reminders, store
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import CampusTask
from campuscue.reminders import (
    DEFAULT_LEADS,
    compose_message,
    describe_lead,
    plan_reminders,
)


def campus(y, m, d, hh=0, mm=0) -> datetime:
    """A campus-local instant, as UTC."""
    return datetime(y, m, d, hh, mm, tzinfo=CAMPUS_TZ).astimezone(timezone.utc)


NO_QUIET = {"start": "00:00", "end": "00:00"}
"""An empty window, so a test that is not about quiet hours is not silently
affected by them."""


class TestLeadSelection:
    def test_homework_gets_a_day_before_two_hours_before_and_the_deadline(self):
        deadline = campus(2026, 8, 14, 23, 59)
        planned = plan_reminders(
            deadline=deadline,
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=NO_QUIET,
        )
        assert [p.lead_minutes for p in planned] == [1440, 120, 0]
        assert [p.fire_at for p in planned] == [
            deadline - timedelta(minutes=1440),
            deadline - timedelta(minutes=120),
            deadline,
        ]

    def test_the_deadline_itself_is_always_included(self):
        """Even a type whose configured leads omit 0 gets a last call: a student
        who ignored the early nudge is exactly who needs it."""
        planned = plan_reminders(
            deadline=campus(2026, 8, 14, 15, 0),
            task_type="activity",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes={"activity": [1440]},
            quiet_hours=NO_QUIET,
        )
        assert 0 in [p.lead_minutes for p in planned]

    def test_leads_that_already_passed_are_dropped_not_fired_late(self):
        """A task extracted the evening before its deadline should get the 2-hour
        nudge and the deadline, not a burst of catch-up pushes for leads that are
        already moot."""
        deadline = campus(2026, 8, 11, 23, 59)
        planned = plan_reminders(
            deadline=deadline,
            task_type="homework",
            now=campus(2026, 8, 11, 18, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=NO_QUIET,
        )
        assert [p.lead_minutes for p in planned] == [120, 0]

    def test_a_deadline_in_the_past_produces_nothing(self):
        planned = plan_reminders(
            deadline=campus(2026, 8, 1, 12, 0),
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=NO_QUIET,
        )
        assert planned == []

    def test_an_undated_task_is_not_scheduled(self):
        """Undated tasks are real ("下周交，时间待通知") and stay on the board;
        there is simply nothing to schedule until someone fills the date in."""
        assert (
            plan_reminders(
                deadline=None,
                task_type="homework",
                now=campus(2026, 8, 10, 9, 0),
            )
            == []
        )

    def test_an_unknown_task_type_falls_back_to_one_day(self):
        planned = plan_reminders(
            deadline=campus(2026, 8, 20, 12, 0),
            task_type="something_new",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes={},
            quiet_hours=NO_QUIET,
        )
        assert [p.lead_minutes for p in planned] == [1440, 0]

    def test_a_partial_profile_still_gets_defaults_for_other_types(self):
        """A student who customised only their exam leads must not lose homework
        reminders."""
        planned = plan_reminders(
            deadline=campus(2026, 8, 20, 12, 0),
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes={"exam": [60]},
            quiet_hours=NO_QUIET,
        )
        assert [p.lead_minutes for p in planned] == [1440, 120, 0]

    def test_results_are_ordered_soonest_first(self):
        planned = plan_reminders(
            deadline=campus(2026, 9, 1, 12, 0),
            task_type="competition",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=NO_QUIET,
        )
        assert planned == sorted(planned, key=lambda p: p.fire_at)


class TestQuietHours:
    QUIET = {"start": "23:00", "end": "07:30"}

    def test_a_reminder_inside_the_window_slides_to_its_end(self):
        """23:00-07:30, deadline Friday 18:00, one day before = Thursday 18:00 is
        fine. Use a deadline that puts the lead at 02:00 instead."""
        deadline = campus(2026, 8, 14, 2, 0)
        planned = plan_reminders(
            deadline=deadline,
            task_type="activity",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes={"activity": [1440]},
            quiet_hours=self.QUIET,
        )
        early = [p for p in planned if p.lead_minutes == 1440][0]
        assert early.shifted is True
        local = early.fire_at.astimezone(CAMPUS_TZ)
        assert (local.hour, local.minute) == (7, 30)
        # Thursday 02:00 was inside the window, so it slid to Thursday 07:30 --
        # forward, and still comfortably before the deadline.
        assert early.fire_at < deadline

    def test_sliding_forward_past_the_deadline_slides_backward_instead(self):
        """Deadline 05:00, lead 2h = 03:00, inside the window. Sliding forward to
        07:30 would land *after* the deadline, turning a reminder into a
        notification of failure -- so it must move back to 22:59 the night
        before."""
        deadline = campus(2026, 8, 14, 5, 0)
        planned = plan_reminders(
            deadline=deadline,
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes={"homework": [120]},
            quiet_hours=self.QUIET,
        )
        early = [p for p in planned if p.lead_minutes == 120][0]
        assert early.shifted is True
        assert early.fire_at < deadline
        local = early.fire_at.astimezone(CAMPUS_TZ)
        assert (local.hour, local.minute) == (23, 0)
        assert local.day == 13

    def test_the_final_call_is_never_silenced_by_quiet_hours(self):
        """The 0-lead reminder cannot be replaced by a later one, so moving it is
        strictly worse than firing it at an inconvenient time."""
        deadline = campus(2026, 8, 14, 2, 0)
        planned = plan_reminders(
            deadline=deadline,
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=self.QUIET,
        )
        final = [p for p in planned if p.lead_minutes == 0][0]
        assert final.fire_at == deadline
        assert final.shifted is False

    def test_a_reminder_outside_the_window_is_untouched(self):
        deadline = campus(2026, 8, 14, 18, 0)
        planned = plan_reminders(
            deadline=deadline,
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours=self.QUIET,
        )
        assert all(p.shifted is False for p in planned)

    def test_two_leads_collapsing_onto_one_minute_are_deduplicated(self):
        """Quiet-hours shifting can push two different leads to the same 07:30.
        Two identical pushes read as a bug."""
        planned = plan_reminders(
            deadline=campus(2026, 8, 14, 12, 0),
            task_type="exam",
            now=campus(2026, 8, 10, 9, 0),
            # 01:00 and 02:00 before a noon deadline are both inside the window
            # on the same night, so both would slide to the same 07:30.
            lead_minutes={"exam": [660, 600]},
            quiet_hours=self.QUIET,
        )
        fire_times = [p.fire_at for p in planned]
        assert len(fire_times) == len(set(fire_times))

    def test_a_malformed_quiet_window_does_not_break_scheduling(self):
        """The column is user-editable JSON. A bad value must degrade to "no quiet
        hours", not lose the student's reminders."""
        planned = plan_reminders(
            deadline=campus(2026, 8, 14, 12, 0),
            task_type="homework",
            now=campus(2026, 8, 10, 9, 0),
            lead_minutes=DEFAULT_LEADS,
            quiet_hours={"start": "not-a-time", "end": None},
        )
        assert len(planned) == 3


class TestPushText:
    def _task(self, **kw) -> CampusTask:
        defaults = {
            "umo": "aiocqhttp:GroupMessage:1",
            "title": "提交软件工程实验三报告",
            "task_type": "homework",
            "deadline": campus(2026, 8, 14, 23, 59),
            "source_group_name": "软件工程课程群",
            "source_sender_name": "张老师",
        }
        defaults.update(kw)
        return CampusTask(**defaults)

    def test_the_title_is_in_the_first_two_lines(self):
        """QQ truncates notification previews hard, so the student must be able to
        tell from a lock screen whether to open it."""
        text = compose_message(self._task(), "提前 1 天")
        assert self._task().title in text.split("\n")[1]

    def test_the_deadline_renders_in_campus_time(self):
        """The 8-hour timezone bug would show up here as 15:59."""
        text = compose_message(self._task(), "提前 1 天")
        assert "08-14 23:59" in text

    def test_an_inferred_time_says_so(self):
        text = compose_message(self._task(deadline_is_explicit=False), "提前 1 天")
        assert "推断" in text

    def test_items_and_location_appear_when_present(self):
        text = compose_message(
            self._task(task_type="exam", location="3教405", items=["身份证", "校园卡"]),
            "提前 2 天",
        )
        assert "3教405" in text
        assert "身份证" in text and "校园卡" in text

    def test_an_undated_task_still_produces_a_message(self):
        text = compose_message(self._task(deadline=None), "提醒")
        assert self._task().title in text
        assert "截止" not in text

    def test_provenance_comes_last(self):
        text = compose_message(self._task(), "提前 1 天")
        assert text.strip().endswith("来自 软件工程课程群 · 张老师")


@pytest.mark.parametrize(
    ("minutes", "expected"),
    [
        (1440, "提前 1 天"),
        (2880, "提前 2 天"),
        (120, "提前 2 小时"),
        (720, "提前 12 小时"),
        (90, "提前 90 分钟"),
    ],
)
def test_describe_lead_uses_the_largest_exact_unit(minutes, expected):
    assert describe_lead(minutes) == expected


# =========================================================================
# resync_all -- scope
# =========================================================================


class FakeCron:
    """Enough of CronJobManager to observe which rows resync deletes.

    A real manager would need a started APScheduler; what is under test is the
    bookkeeping, so jobs are dicts and ``_fire`` is never called.
    """

    def __init__(self) -> None:
        self.jobs: dict[str, SimpleNamespace] = {}
        self.db = SimpleNamespace(update_cron_job=self._noop)
        self.deleted: list[str] = []

    async def _noop(self, *a, **kw) -> None:
        return None

    async def add_basic_job(self, *, name: str, **kw) -> SimpleNamespace:
        job_id = f"job-{len(self.jobs)}-{uuid.uuid4().hex[:6]}"
        job = SimpleNamespace(job_id=job_id, name=name, job_type="basic")
        self.jobs[job_id] = job
        return job

    async def list_jobs(self, job_type: str | None = None) -> list:
        return [j for j in self.jobs.values() if not job_type or j.job_type == job_type]

    async def delete_job(self, job_id: str) -> None:
        self.jobs.pop(job_id, None)
        self.deleted.append(job_id)


@pytest_asyncio.fixture
async def scheduled(tmp_path, monkeypatch):
    """Two groups, one task each, both with live reminders."""
    db = SQLiteDatabase(str(tmp_path / "resync.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    cron = FakeCron()
    monkeypatch.setattr(reminders, "_cron", cron)
    monkeypatch.setattr(reminders, "_ctx", None)

    deadline = datetime.now(timezone.utc) + timedelta(days=6)
    made = {}
    for umo, title in (("g:A", "A 的作业"), ("g:B", "B 的作业")):
        task = await store.create_task(
            CampusTask(
                umo=umo,
                title=title,
                task_type="homework",
                status="active",
                deadline=deadline,
                confidence=1.0,
            )
        )
        await reminders.schedule_for_task(task)
        made[umo] = task

    try:
        yield cron, made
    finally:
        await db.engine.dispose()


def jobs_for(cron: FakeCron, task_id: str) -> list:
    return [j for j in cron.jobs.values() if f":{task_id}:" in j.name]


@pytest.mark.asyncio
async def test_a_scoped_resync_leaves_other_groups_scheduled(scheduled):
    """The bug this pins, found on a running instance rather than by reading:

    saving preferences for one group calls ``resync_all(umo)``, which swept every
    ``campuscue:remind`` row in the table and rebuilt only that group's. Every
    other group was left with tasks pointing at deleted jobs -- no error, no log
    line, and nothing would fire until the next restart. On a demo laptop that is
    the whole product silently off.
    """
    cron, made = scheduled
    before = len(jobs_for(cron, made["g:B"].task_id))
    assert before, "fixture did not schedule anything for the other group"

    await reminders.resync_all("g:A")

    assert jobs_for(cron, made["g:A"].task_id), "the scoped group must be rebuilt"
    assert len(jobs_for(cron, made["g:B"].task_id)) == before


@pytest.mark.asyncio
async def test_a_scoped_resync_replaces_rather_than_duplicates_its_own_jobs(scheduled):
    """The other half: sweeping too little leaves the group's old rows behind and
    a student gets every reminder twice."""
    cron, made = scheduled
    before = len(jobs_for(cron, made["g:A"].task_id))

    await reminders.resync_all("g:A")

    assert len(jobs_for(cron, made["g:A"].task_id)) == before


@pytest.mark.asyncio
async def test_an_unscoped_resync_rebuilds_everything(scheduled):
    """Startup path: every origin reconciled, nothing accumulated."""
    cron, made = scheduled
    total = len(cron.jobs)

    result = await reminders.resync_all()

    assert result["tasks"] == 2
    assert len(cron.jobs) == total


@pytest.mark.asyncio
async def test_startup_covers_a_group_that_has_no_source_row(scheduled):
    """A hand-entered task lives in a group nothing was ever observed in -- a DM,
    or 新建 on a fresh board. Driving the startup resync from source rows alone
    left exactly those tasks unarmed, which is the case a student notices first
    because it is the task they entered themselves.
    """
    cron, _ = scheduled
    task = await store.create_task(
        CampusTask(
            umo="qq:FriendMessage:solo",  # no CampusSource row for this origin
            title="手动录的事",
            task_type="homework",
            status="active",
            deadline=datetime.now(timezone.utc) + timedelta(days=6),
            confidence=1.0,
        )
    )

    await reminders.resync_all()

    assert jobs_for(cron, task.task_id), (
        "startup must schedule tasks whose group has never been observed"
    )


@pytest.mark.asyncio
async def test_a_scoped_resync_clears_jobs_of_a_task_no_longer_active(scheduled):
    """A task completed while the process was down still owns rows. Nothing else
    will ever collect them, so the scoped sweep has to look past the active set."""
    cron, made = scheduled
    task = made["g:A"]
    await store.update_task(task.task_id, status="done")

    await reminders.resync_all("g:A")

    assert jobs_for(cron, task.task_id) == []
