"""M3 Reminder tests — schema migration, reminder policy, service lifecycle,
APScheduler integration, runtime resync, local real scheduler acceptance.

All deterministic: FixedClock + fixed timezone. Never touches real QQ/NapCat.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.storage.enums import ReminderStatus, ReminderType, TaskStatus

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)  # Mon 2026-08-10 08:00 +08


def _deadline(days: int, hours: int = 0, *, tz: ZoneInfo = TZ) -> datetime:
    """Deadline in local tz converted to UTC, days/hours ahead of NOW."""
    local = NOW.astimezone(tz) + timedelta(days=days, hours=hours)
    return local.astimezone(timezone.utc)


def _utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, 0, tzinfo=timezone.utc)


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "m3.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
def clock():
    from campuscue.storage.clock import FixedClock

    return FixedClock(NOW)


@pytest.fixture
def repos(db, clock):
    from campuscue.repositories.repositories import (
        ReminderRepository,
        SourceRepository,
        TaskRepository,
    )

    return {
        "tasks": TaskRepository(db.session, clock=clock),
        "reminders": ReminderRepository(db.session, clock=clock),
        "sources": SourceRepository(db.session, clock=clock),
    }


def _make_task(repos, *, title="作业", deadline=None, status="pending", **kw):
    return asyncio.get_event_loop().run_until_complete(
        repos["tasks"].create(
            title=title, deadline=deadline, status=status, source_id=None, source_message_id=None, **kw
        )
    )


async def _create_task_async(repos, *, title="作业", deadline=None, status="pending", **kw):
    return await repos["tasks"].create(
        title=title, deadline=deadline, status=status, source_id=None, source_message_id=None, **kw
    )


# ------------------------------------------------------------------ A/B/C: schema

class TestSchemaMigration:
    def test_fresh_db_bootstraps_v2(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig

        p = tmp_path / "fresh.db"
        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())
        conn = sqlite3.connect(str(p))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        conn.close()
        assert "reminders" in tables
        assert version == 2
        asyncio.run(db.dispose())

    def test_v1_db_migrates_preserving_data(self, tmp_path):
        """A: v1 DB with existing task data -> migrate -> task present,
        reminders table present, schema v2."""
        import sqlite3

        from campuscue.storage.database import Database, DatabaseConfig

        p = tmp_path / "v1.db"
        # build a v1 database manually (same shape as M2 schema v1)
        conn = sqlite3.connect(str(p))
        conn.executescript(
            """
            CREATE TABLE sources (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                platform VARCHAR(32) NOT NULL, conversation_id VARCHAR(64) NOT NULL,
                name VARCHAR(128) NOT NULL, enabled BOOLEAN NOT NULL,
                auto_extract BOOLEAN NOT NULL, context_window INTEGER NOT NULL,
                privacy_policy VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            );
            CREATE TABLE tasks (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(256) NOT NULL, description TEXT,
                category VARCHAR(32) NOT NULL, course VARCHAR(128),
                deadline DATETIME, status VARCHAR(32) NOT NULL,
                priority VARCHAR(16) NOT NULL, confidence FLOAT,
                dedup_key VARCHAR(128), source_id INTEGER,
                source_message_id VARCHAR(64), source_text_reference TEXT,
                created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
            );
            CREATE TABLE extractions (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                source_id INTEGER, source_message_id VARCHAR(64) NOT NULL,
                trace_id VARCHAR(64) NOT NULL, provider VARCHAR(64), model VARCHAR(128),
                status VARCHAR(16) NOT NULL, confidence FLOAT, raw_result TEXT,
                normalized_result TEXT, audit TEXT, error TEXT,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE provider_configs (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(64) NOT NULL, provider_type VARCHAR(32) NOT NULL,
                base_url VARCHAR(256) NOT NULL, model VARCHAR(128) NOT NULL,
                temperature FLOAT, max_tokens INTEGER, max_context_tokens INTEGER,
                timeout_s FLOAT NOT NULL, secret_reference VARCHAR(128),
                enabled BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            CREATE TABLE schema_meta (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, schema_version INTEGER NOT NULL UNIQUE);
            INSERT INTO schema_meta (schema_version) VALUES (1);
            INSERT INTO tasks (title, category, status, priority, created_at, updated_at)
            VALUES ('旧任务', 'homework', 'pending', 'normal', '2026-08-01 00:00:00', '2026-08-01 00:00:00');
            """
        )
        conn.commit()
        conn.close()

        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())
        conn = sqlite3.connect(str(p))
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        tasks = conn.execute("SELECT title, status FROM tasks").fetchall()
        conn.close()
        assert "reminders" in tables
        assert version == 2
        assert ("旧任务", "pending") in tasks  # data preserved
        asyncio.run(db.dispose())

    def test_unknown_newer_schema_refused_zero_mutation(self, tmp_path):
        """C: newer/unknown schema version -> refused, database unchanged."""
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        p = tmp_path / "future.db"
        conn = sqlite3.connect(str(p))
        conn.executescript(
            "CREATE TABLE schema_meta (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, schema_version INTEGER NOT NULL UNIQUE);"
            "INSERT INTO schema_meta (schema_version) VALUES (99);"
        )
        conn.commit()
        before = open(str(p), "rb").read()
        conn.close()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError):
            asyncio.run(db.initialize())
        after = open(str(p), "rb").read()
        assert after == before  # ZERO MUTATION


# ------------------------------------------------------------------ D/E/F/G/H: policy

class TestReminderPolicy:
    def _task(self, *, deadline=None, status="pending"):
        from campuscue.storage.models import Task

        return Task(
            id=1, title="作业", description=None, category="homework", course=None,
            deadline=deadline, status=status, priority="normal", confidence=0.9,
            dedup_key=None, source_id=None, source_message_id=None,
            source_text_reference=None,
            created_at=NOW, updated_at=NOW,
        )

    def test_no_deadline_zero_reminders(self):
        """D: task with no deadline -> zero reminders."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        r = plan_desired_reminders(task=self._task(deadline=None), now=NOW, tz=TZ)
        assert r == []

    def test_pending_confirm_zero_reminders(self):
        """E: pending_confirm task -> zero active reminders."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        r = plan_desired_reminders(
            task=self._task(deadline=_deadline(3), status="pending_confirm"), now=NOW, tz=TZ
        )
        assert r == []

    def test_pending_with_deadline_three_reminders(self):
        """F: pending task with deadline -> three reminders when all future."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        d = _deadline(5, 12)  # 5 days 12h ahead
        r = plan_desired_reminders(task=self._task(deadline=d), now=NOW, tz=TZ)
        types = sorted(x.type for x in r)
        assert types == ["day_before", "deadline", "hours_before"]
        # offsets: deadline - 1d, deadline - 2h, deadline
        assert min(x.trigger_at_utc for x in r) == d - timedelta(days=1)
        assert max(x.trigger_at_utc for x in r) == d

    def test_less_than_60s_discarded(self):
        """G: <60s reminder candidates discarded."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        d = NOW + timedelta(seconds=30)  # deadline in 30s -> hours_before/deadline past, day_before past
        r = plan_desired_reminders(task=self._task(deadline=d), now=NOW, tz=TZ)
        assert r == []

    def test_past_candidates_discarded_no_backfill(self):
        """H: past reminder candidates discarded (no backfill)."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        d = NOW + timedelta(seconds=30)
        r = plan_desired_reminders(task=self._task(deadline=d), now=NOW, tz=TZ)
        assert all(x.trigger_at_utc > NOW for x in r) or r == []

    def test_quiet_hours_folding(self):
        """I: quiet-hours folding — a 23:30 trigger folds to next 08:00."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        # deadline 2026-08-14 23:30 +08 -> hours_before = 21:30 (outside quiet),
        # day_before = 2026-08-13 23:30 +08 (inside quiet 23-08 -> folds to 08-14 08:00)
        local_deadline = datetime(2026, 8, 14, 23, 30, tzinfo=TZ)
        d = local_deadline.astimezone(timezone.utc)
        r = plan_desired_reminders(task=self._task(deadline=d), now=NOW, tz=TZ)
        day_before = [x for x in r if x.type == "day_before"]
        assert day_before
        folded_local = day_before[0].trigger_at_utc.astimezone(TZ)
        assert folded_local.hour == 8  # folded to 08:00 local
        assert folded_local.day == 14  # 2026-08-14 08:00 local
        # hours_before (21:30) NOT folded:
        hours_before = [x for x in r if x.type == "hours_before"]
        assert hours_before
        assert hours_before[0].trigger_at_utc.astimezone(TZ).hour == 21

    def test_folded_same_minute_dedup(self):
        """J: folded same-minute dedup — two intents collapse to one effective."""
        from campuscue.tasks.reminder_policy import (
            DEFAULT_POLICY,
            DesiredReminder,
            plan_desired_reminders,
        )

        # deadline 08-14 23:30 +08: hours_before = 21:30 (kept), day_before =
        # 08-13 23:30 folds to 08-14 08:00, deadline = 23:30 — all distinct.
        # To force a SAME-MINUTE collision we craft two intents at one minute
        # via a custom policy where day_before offset == hours_before offset.
        from datetime import timedelta as td

        from campuscue.storage.models import Task

        colliding = datetime(2026, 8, 14, 8, 0, tzinfo=TZ)  # 08-14 08:00 +08
        task = Task(
            id=1, title="作业", description=None, category="homework", course=None,
            deadline=colliding.astimezone(timezone.utc), status="pending",
            priority="normal", confidence=0.9, dedup_key=None, source_id=None,
            source_message_id=None, source_text_reference=None,
            created_at=NOW, updated_at=NOW,
        )
        # day_before offset 0h and hours_before offset 0h -> both at deadline minute
        class CollidingPolicy:
            day_before_offset = td(hours=0)
            hours_before_offset = td(hours=0)
            min_lead_seconds = 60
            quiet_start_hour = 23
            quiet_end_hour = 8

        r = plan_desired_reminders(task=task, now=NOW, tz=TZ, policy=CollidingPolicy())
        # three candidates, three same minute -> collapse to ONE
        assert len(r) == 1
        assert r[0].type == "day_before"  # precedence day_before > hours_before > deadline


# ------------------------------------------------------------------ service lifecycle

class TestReminderService:
    @pytest.mark.asyncio
    async def test_create_plans_reminders(self, db, clock, repos):
        """F via service: pending task with deadline -> 3 reminder facts."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        result = await svc.plan_reminders(task)
        assert result.planned == 3
        rows = await svc.list_for_task(task.id)
        assert len(rows) == 3
        assert all(r.status == "scheduled" for r in rows)
        types = sorted(r.type for r in rows)
        assert types == ["day_before", "deadline", "hours_before"]

    @pytest.mark.asyncio
    async def test_repeated_plan_idempotent(self, db, clock, repos):
        """K: repeated plan is idempotent — no duplicate rows/jobs."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await svc.plan_reminders(task)
        await svc.plan_reminders(task)
        await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        # old rows cancelled, only latest plan scheduled
        scheduled = [r for r in rows if r.status == "scheduled"]
        assert len(scheduled) == 3
        assert sum(1 for r in rows if r.status == "cancelled") == 6

    @pytest.mark.asyncio
    async def test_change_deadline_replaces_plan(self, db, clock, repos):
        """L: deadline change removes old plan and installs new plan."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler
        from campuscue.services.task_service import TaskService

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await ts.change_deadline(task.id, _deadline(9, 6))
        rows = await repos["reminders"].list_for_task(task.id)
        scheduled = [r for r in rows if r.status == "scheduled"]
        assert len(scheduled) == 3
        assert all(r.trigger_at < _deadline(5, 6) + timedelta(hours=1) or r.trigger_at > _deadline(5, 6) + timedelta(hours=2) for r in scheduled)
        assert all(r.status == "cancelled" for r in rows if r not in scheduled)

    @pytest.mark.asyncio
    async def test_complete_cancels(self, db, clock, repos):
        """M: complete cancels reminders."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler
        from campuscue.services.task_service import TaskService

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await ts.complete(task.id)
        rows = await repos["reminders"].list_for_task(task.id)
        assert all(r.status == "cancelled" for r in rows)

    @pytest.mark.asyncio
    async def test_dismiss_cancels(self, db, clock, repos):
        """N: dismiss cancels reminders."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler
        from campuscue.services.task_service import TaskService

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await ts.dismiss(task.id)
        rows = await repos["reminders"].list_for_task(task.id)
        assert all(r.status == "cancelled" for r in rows)

    @pytest.mark.asyncio
    async def test_delete_cleans_reminders_fk_safe(self, db, clock, repos):
        """O: delete cleans reminders/jobs (FK-safe order)."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler
        from campuscue.services.task_service import TaskService

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await ts.delete(task.id)
        rows = await repos["reminders"].list_for_task(task.id)
        assert rows == []  # hard-deleted
        from campuscue.repositories.repositories import NotFoundError

        with pytest.raises(NotFoundError):
            await repos["tasks"].get(task.id)

    @pytest.mark.asyncio
    async def test_fire_rechecks_latest_state(self, db, clock, repos):
        """P: fire re-checks latest task state (done -> no delivery)."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        deliveries = []

        class Sink:
            async def deliver(self, *, reminder, task):
                deliveries.append(reminder.id)

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        svc.set_delivery(Sink())
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        result = await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        scheduled = [r for r in rows if r.status == "scheduled"]
        assert deliveries == []
        # complete the task -> fire should skip + cancel
        await repos["tasks"].set_status(task.id, "done")
        await svc.fire(scheduled[0].id)
        assert deliveries == []  # zero callbacks for done task
        row = await repos["reminders"].get(scheduled[0].id)
        assert row.status == "cancelled"

    @pytest.mark.asyncio
    async def test_fire_delivers_when_active(self, db, clock, repos):
        """P2: due reminder on active pending task -> one delivery callback."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        deliveries = []

        class Sink:
            async def deliver(self, *, reminder, task):
                deliveries.append((reminder.id, task.id))

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        svc.set_delivery(Sink())
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        fired = await svc.fire(rows[0].id)
        assert fired is True
        assert deliveries == [(rows[0].id, task.id)]
        row = await repos["reminders"].get(rows[0].id)
        assert row.status == "fired"
        assert row.last_run is not None

    @pytest.mark.asyncio
    async def test_fire_deleted_task_cancels(self, db, clock, repos):
        """P3: deleted task -> zero callbacks, fact cancelled."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        deliveries = []

        class Sink:
            async def deliver(self, *, reminder, task):
                deliveries.append(reminder.id)

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        svc.set_delivery(Sink())
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        from campuscue.services.task_service import TaskService
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        await ts.delete(task.id)  # FK-safe service delete
        await svc.fire(rows[0].id)
        assert deliveries == []


# ------------------------------------------------------------------ resync

class TestResync:
    @pytest.mark.asyncio
    async def test_resync_rebuilds_jobs_no_duplicates(self, db, clock, repos):
        """Q+R: resync rebuilds scheduler jobs from DB without duplicating
        facts or jobs."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        sched = NoopScheduler()
        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=sched, clock=clock, timezone=TZ)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await svc.plan_reminders(task)
        # simulate restart: fresh service, same DB
        svc2 = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        installed = await svc2.resync_all()
        assert installed == 3
        rows = await repos["reminders"].list_for_task(task.id)
        assert len([r for r in rows if r.status == "scheduled"]) == 3  # no dup facts

    @pytest.mark.asyncio
    async def test_resync_skips_missed_and_inactive(self, db, clock, repos):
        """S: missed during downtime not backfilled; done task not resurrected."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        # task whose deadline already passed while "down" (fact exists but trigger in past)
        task = await _create_task_async(repos, deadline=NOW - timedelta(days=1))
        # create a scheduled fact directly (as if planned before downtime)
        past = await repos["reminders"].create(task_id=task.id, trigger_at=NOW - timedelta(hours=1), type="deadline")
        done_task = await _create_task_async(repos, title="已办", deadline=_deadline(5, 6), status="done")
        future_for_done = await repos["reminders"].create(task_id=done_task.id, trigger_at=_deadline(5, 6), type="deadline")

        installed = await svc.resync_all()
        assert installed == 0  # both skipped (past trigger + done task)
        assert (await repos["reminders"].get(past.id)).status == "cancelled"
        assert (await repos["reminders"].get(future_for_done.id)).status == "cancelled"

    @pytest.mark.asyncio
    async def test_resync_no_firing_expired(self, db, clock, repos):
        """S2: restart never fires reminders expired during downtime."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler

        deliveries = []

        class Sink:
            async def deliver(self, *, reminder, task):
                deliveries.append(reminder.id)

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        svc.set_delivery(Sink())
        task = await _create_task_async(repos, deadline=NOW - timedelta(days=1))
        past = await repos["reminders"].create(task_id=task.id, trigger_at=NOW - timedelta(hours=1), type="deadline")
        await svc.resync_all()
        assert deliveries == []  # never backfilled


# ------------------------------------------------------------------ APScheduler real

class TestReminderSchedulerReal:
    @pytest.mark.asyncio
    async def test_real_scheduler_fires_due(self, db, clock, repos):
        """Local REAL scheduler acceptance (part 1): APScheduler 3.11 actually
        fires a due job -> ReminderService.fire -> delivery sink."""
        from campuscue.services.reminder_scheduler import ReminderScheduler
        from campuscue.services.reminder_service import ReminderService, reminder_job_id

        fired = []

        async def fire_cb(reminder_id):
            fired.append(reminder_id)

        sched = ReminderScheduler(fire_callback=fire_cb)
        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=sched, clock=clock, timezone=TZ)
        # NOTE: APScheduler uses the REAL wall clock (AsyncIOScheduler), not the
        # injected FixedClock. Use a genuine near-future deadline (wall clock
        # now + 2s) so the derived deadline job actually fires during the test.
        # Relative to the FixedClock (2026-08-10), all three intents are future
        # -> 3 facts/3 jobs; only the deadline job is near-future in REAL time.
        wall_now = datetime.now(timezone.utc)
        task = await _create_task_async(repos, deadline=wall_now + timedelta(seconds=2))
        await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        scheduled = sorted([r for r in rows if r.status == "scheduled"], key=lambda r: r.trigger_at)
        assert sched.job_count() == 3  # three derived jobs installed

        sched.start()
        await asyncio.sleep(3.2)  # let the ~2s deadline job fire
        await sched.shutdown(wait=True)

        # only the deadline intent fires (day_before/hours_before are real-time
        # past -> misfire_grace_time=1 drops them)
        assert len(fired) == 1
        assert fired[0] == scheduled[-1].id  # the deadline reminder

    @pytest.mark.asyncio
    async def test_scheduler_stable_job_id_and_replacement(self, db, clock, repos):
        """T: deterministic stable job id + replace_existing idempotency."""
        from campuscue.services.reminder_scheduler import ReminderScheduler
        from campuscue.services.reminder_service import ReminderService, reminder_job_id

        sched = ReminderScheduler(fire_callback=lambda rid: None)
        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=sched, clock=clock, timezone=TZ)
        task = await _create_task_async(repos, deadline=_deadline(5, 6))
        await svc.plan_reminders(task)
        rows = await repos["reminders"].list_for_task(task.id)
        scheduled = [r for r in rows if r.status == "scheduled"]
        assert sched.job_count() == 3
        # idempotent re-plan: old facts cancelled, NEW facts + jobs installed —
        # same logical count, deterministic job ids for the NEW facts
        await svc.plan_reminders(task)
        assert sched.job_count() == 3  # still 3, no duplicate jobs
        rows2 = await repos["reminders"].list_for_task(task.id)
        scheduled2 = [r for r in rows2 if r.status == "scheduled"]
        assert len(scheduled2) == 3  # no duplicate facts
        assert all(r.id > scheduled[-1].id for r in scheduled2)  # new rows
        for r in scheduled2:
            assert sched.get_job(reminder_job_id(r.id)) is not None  # stable id present

    @pytest.mark.asyncio
    async def test_scheduler_shutdown_no_background_work(self, db, clock, repos):
        """U: scheduler shutdown leaves no owned background work."""
        from campuscue.services.reminder_scheduler import ReminderScheduler

        sched = ReminderScheduler(fire_callback=lambda rid: None)
        sched.start()
        await asyncio.sleep(0.2)
        assert sched.running is True
        await sched.shutdown(wait=True)
        assert sched.running is False
        assert sched.job_count() == 0


# ------------------------------------------------------------------ clock/timezone

class TestClockTimezone:
    def test_storage_aware_utc(self, db, clock, repos):
        """V: time storage remains aware UTC (no naive)."""
        import asyncio as aio

        d = _deadline(3, 6)
        task = asyncio.run(_create_task_async(repos, deadline=d))
        t = asyncio.run(
            repos["reminders"].create(task_id=task.id, trigger_at=d, type="deadline")
        )
        assert t.trigger_at.tzinfo is not None
        assert t.trigger_at == d.astimezone(timezone.utc)

    def test_policy_dst_boundary(self):
        """V2: DST-observing timezone (America/New_York) arithmetic is sane."""
        from campuscue.storage.models import Task
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        ny = ZoneInfo("America/New_York")
        now_utc = _utc(2026, 3, 1, 12, 0)
        # deadline 2026-03-10 00:00 NY (after spring-forward on Mar 8)
        local_deadline = datetime(2026, 3, 10, 0, 0, tzinfo=ny)
        task = Task(
            id=1, title="作业", description=None, category="homework", course=None,
            deadline=local_deadline.astimezone(timezone.utc), status="pending",
            priority="normal", confidence=0.9, dedup_key=None, source_id=None,
            source_message_id=None, source_text_reference=None,
            created_at=now_utc, updated_at=now_utc,
        )
        r = plan_desired_reminders(task=task, now=now_utc, tz=ny)
        assert len(r) == 3
        assert all(x.trigger_at_utc.tzinfo is not None for x in r)


# ------------------------------------------------------------------ X: TaskService gate

class TestTaskServiceGate:
    @pytest.mark.asyncio
    async def test_task_service_remains_only_mutation_path(self, db, clock, repos):
        """X: TaskService is the only business mutation path — pipeline uses it;
        repository create is persistence primitive only."""
        from campuscue.services.reminder_service import ReminderService, NoopScheduler
        from campuscue.services.task_service import TaskService

        svc = ReminderService(repos["reminders"], repos["tasks"], scheduler=NoopScheduler(), clock=clock, timezone=TZ)
        ts = TaskService(repos["tasks"], clock=clock, reminder_service=svc)
        from campuscue.tasks.models import TaskCandidate

        task = await ts.create_task(
            TaskCandidate(
                title="作业", category="homework", course=None, deadline=_deadline(5, 6),
                description=None, confidence=0.9, dedup_key="k1",
                source_id=None, source_message_id="m1", source_text_reference="原文",
                pending_confirm=False,
            )
        )
        assert task.created
        # reminder planned automatically through TaskService.create_task
        rows = await repos["reminders"].list_for_task(task.task.id)
        assert len([r for r in rows if r.status == "scheduled"]) == 3
