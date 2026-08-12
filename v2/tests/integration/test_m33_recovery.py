"""M3.3 Final Recovery Fix regression tests (external review round).

A. resync_all is TRUE BUSINESS RECONCILIATION:
   canonical Tasks -> reconcile Reminder facts -> rebuild scheduler jobs.
   Heals: M2->M3 upgraded tasks (empty reminders), crash gaps (task committed,
   reminder planning never ran), partial drift (2 of 3 facts present).
   Idempotent: unchanged restart keeps fact IDs stable, no cancelled-history
   growth, no duplicate active facts.
B. current-version (v2) database structure validated read-only BEFORE
   create_all — malformed current-v2 refuses zero-mutation.
C. (docs) 17_MILESTONES gate state fixed separately.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.storage.enums import ReminderStatus, TaskStatus

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)


def _deadline(days: int, hours: int = 0) -> datetime:
    local = NOW.astimezone(TZ) + timedelta(days=days, hours=hours)
    return local.astimezone(timezone.utc)


@pytest.fixture
def clock():
    from campuscue.storage.clock import FixedClock

    return FixedClock(NOW)


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "m33.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
def repos(db, clock):
    from campuscue.repositories.repositories import (
        ReminderRepository,
        TaskRepository,
    )

    return {
        "tasks": TaskRepository(db.session, clock=clock),
        "reminders": ReminderRepository(db.session, clock=clock),
    }


async def _task(repos, *, title="作业", deadline, status="pending"):
    return await repos["tasks"].create(
        title=title, deadline=deadline, status=status,
        source_id=None, source_message_id=None,
    )


class _TrackingScheduler:
    def __init__(self):
        self.jobs = set()

    async def schedule(self, *, job_id, run_at, reminder_id):
        self.jobs.add(job_id)

    async def unschedule(self, job_id):
        self.jobs.discard(job_id)

    async def clear_all(self):
        self.jobs.clear()


def _svc(repos, clock, sched=None):
    from campuscue.services.reminder_service import ReminderService

    return ReminderService(
        repos["reminders"], repos["tasks"],
        scheduler=sched or _TrackingScheduler(),
        clock=clock, timezone=TZ,
    )


# ------------------------------------------------------------------ A: migration backfill

class TestMigrationBackfill:
    def test_v1_task_receives_reminders_after_startup_resync(self, tmp_path, clock):
        """M2 v1 DB with pending task + future deadline -> migrate -> startup
        resync -> reminder facts + jobs created. Existing task preserved."""
        from campuscue.repositories.repositories import (
            ReminderRepository,
            TaskRepository,
        )
        from campuscue.storage.database import Database, DatabaseConfig

        p = tmp_path / "v1backfill.db"
        # build VALID v1 db with one pending task + future deadline
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
            """
        )
        d = _deadline(5, 6).astimezone(timezone.utc)
        conn.execute(
            "INSERT INTO tasks (title, category, status, priority, deadline, created_at, updated_at)"
            " VALUES ('旧任务', 'homework', 'pending', 'normal', ?, '2026-08-01', '2026-08-01')",
            (d.strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.commit()
        conn.close()

        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())  # v1 -> v2 migration

        sf = db.session
        tasks = TaskRepository(sf, clock=clock)
        reminders = ReminderRepository(sf, clock=clock)
        sched = _TrackingScheduler()
        svc = _svc({"tasks": tasks, "reminders": reminders}, clock, sched)

        asyncio.run(svc.resync_all())  # startup reconciliation

        all_tasks = asyncio.run(tasks.list_all())
        assert len(all_tasks) == 1 and all_tasks[0].title == "旧任务"  # preserved
        facts = asyncio.run(reminders.list_for_task(all_tasks[0].id))
        scheduled = [r for r in facts if r.status == "scheduled"]
        assert len(scheduled) == 3  # backfilled from task
        assert len(sched.jobs) == 3  # derived jobs

        # schema version now v2
        conn = sqlite3.connect(str(p))
        assert conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0] == 2
        conn.close()

        # simulate restart: fresh service + scheduler, same DB
        sched2 = _TrackingScheduler()
        svc2 = _svc({"tasks": tasks, "reminders": reminders}, clock, sched2)
        asyncio.run(svc2.resync_all())
        facts2 = asyncio.run(reminders.list_for_task(all_tasks[0].id))
        scheduled2 = [r for r in facts2 if r.status == "scheduled"]
        assert len(scheduled2) == 3  # no duplicate active facts
        assert len(sched2.jobs) == 3
        # matching fact IDs remain stable across restart (no recreate)
        assert sorted(r.id for r in scheduled2) == sorted(r.id for r in scheduled)
        # no needless cancelled-history growth from restart
        assert sum(1 for r in facts2 if r.status == "cancelled") == 0
        asyncio.run(db.dispose())


# ------------------------------------------------------------------ A: crash-gap healing

class TestCrashGapHealing:
    @pytest.mark.asyncio
    async def test_missing_facts_heal_and_idempotent(self, db, clock, repos):
        """Crash gap: pending task with future deadline, reminder rows absent
        (task committed, planning died). resync reconstructs facts + jobs;
        second resync is idempotent (same IDs, no churn)."""
        sched = _TrackingScheduler()
        svc = _svc(repos, clock, sched)
        task = await _task(repos, deadline=_deadline(5, 6))
        # NO reminder facts exist (crash gap)
        assert await repos["reminders"].list_for_task(task.id) == []

        installed = await svc.resync_all()
        assert installed == 3
        facts = await repos["reminders"].list_for_task(task.id)
        scheduled = [r for r in facts if r.status == "scheduled"]
        assert len(scheduled) == 3
        ids_first = sorted(r.id for r in scheduled)

        # second resync: same IDs, no new cancelled rows, same jobs
        installed2 = await svc.resync_all()
        assert installed2 == 3
        facts2 = await repos["reminders"].list_for_task(task.id)
        scheduled2 = [r for r in facts2 if r.status == "scheduled"]
        assert sorted(r.id for r in scheduled2) == ids_first
        assert sum(1 for r in facts2 if r.status == "cancelled") == 0
        assert len(sched.jobs) == 3


# ------------------------------------------------------------------ A: partial drift

class TestPartialDrift:
    @pytest.mark.asyncio
    async def test_partial_plan_heals_without_replacing_valid(self, db, clock, repos):
        """Partial drift: only 2 of 3 desired facts exist. resync KEEPS the 2
        matching facts, creates only the missing 1, schedules all 3."""
        sched = _TrackingScheduler()
        svc = _svc(repos, clock, sched)
        task = await _task(repos, deadline=_deadline(5, 6))
        # full plan first
        await svc.plan_reminders(task)
        facts = await repos["reminders"].list_for_task(task.id)
        scheduled = sorted([r for r in facts if r.status == "scheduled"], key=lambda r: r.trigger_at)
        assert len(scheduled) == 3
        kept_ids = {scheduled[0].id, scheduled[1].id}  # keep two, drop one
        # simulate drift: cancel one desired fact, add one stale fact
        await repos["reminders"].mark_cancelled(scheduled[2].id, now=clock.utcnow())
        stale = await repos["reminders"].create(
            task_id=task.id, trigger_at=_deadline(3, 6), type="deadline"  # not in desired set
        )

        await svc.resync_all()

        facts2 = await repos["reminders"].list_for_task(task.id)
        scheduled2 = [r for r in facts2 if r.status == "scheduled"]
        assert len(scheduled2) == 3  # healed to full plan
        # the 2 kept facts retained identity (not recreated)
        assert kept_ids <= {r.id for r in scheduled2}
        # stale fact cancelled, not scheduled
        assert (await repos["reminders"].get(stale.id)).status == "cancelled"
        assert len(sched.jobs) == 3


# ------------------------------------------------------------------ A: non-pending/no-deadline

class TestInactiveTasks:
    @pytest.mark.asyncio
    async def test_non_pending_and_no_deadline_have_no_active_reminders(self, db, clock, repos):
        """done/dismissed/pending_confirm/no-deadline tasks must have no
        scheduled reminders (stale facts cancelled on resync)."""
        sched = _TrackingScheduler()
        svc = _svc(repos, clock, sched)
        done_task = await _task(repos, title="已办", deadline=_deadline(5, 6), status="done")
        nodl_task = await _task(repos, title="无截止", deadline=None)
        pc_task = await _task(repos, title="待确认", deadline=_deadline(5, 6), status="pending_confirm")
        # inject stale facts as if left behind
        stale_done = await repos["reminders"].create(task_id=done_task.id, trigger_at=_deadline(5, 6), type="deadline")
        stale_nodl = await repos["reminders"].create(task_id=nodl_task.id, trigger_at=_deadline(5, 6), type="deadline")
        stale_pc = await repos["reminders"].create(task_id=pc_task.id, trigger_at=_deadline(5, 6), type="deadline")

        installed = await svc.resync_all()
        assert installed == 0  # nothing schedulable
        assert (await repos["reminders"].get(stale_done.id)).status == "cancelled"
        assert (await repos["reminders"].get(stale_nodl.id)).status == "cancelled"
        assert (await repos["reminders"].get(stale_pc.id)).status == "cancelled"
        assert sched.jobs == set()


# ------------------------------------------------------------------ B: current-v2 structural precheck

class TestCurrentV2StructuralPrecheck:
    def _build(self, path, *, with_reminders=True, tasks_ok=True, version=2):
        conn = sqlite3.connect(str(path))
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
            """
        )
        if tasks_ok:
            conn.executescript(
                """
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
                """
            )
        else:
            conn.execute("CREATE TABLE tasks (id INTEGER NOT NULL PRIMARY KEY);")
        if with_reminders:
            conn.executescript(
                """
                CREATE TABLE reminders (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id),
                    trigger_at DATETIME NOT NULL, type VARCHAR(16) NOT NULL,
                    status VARCHAR(16) NOT NULL, last_run DATETIME, error TEXT,
                    job_id VARCHAR(64), created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                """
            )
        conn.execute("INSERT INTO schema_meta (schema_version) VALUES (?)", (version,))
        conn.commit()
        conn.close()

    def test_v2_missing_reminders_table_refused_zero_mutation(self, tmp_path):
        """schema_meta=2 but reminders table missing -> REFUSE, zero mutation."""
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        p = tmp_path / "no-reminders.db"
        self._build(p, with_reminders=False)
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="reminders"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_v2_tasks_missing_critical_column_refused(self, tmp_path):
        """schema_meta=2 + tasks missing a critical column -> REFUSE, zero
        mutation (create_all must not repair it silently)."""
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        p = tmp_path / "bad-tasks.db"
        self._build(p, tasks_ok=False)
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="missing required column"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_valid_v2_reopens_idempotently(self, tmp_path):
        """Valid current-v2 DB -> reopen PASS, no schema mutation."""
        from campuscue.storage.database import Database, DatabaseConfig

        p = tmp_path / "valid-v2.db"
        self._build(p)  # valid v2 shape (reminders present, tasks ok)
        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())  # must not raise
        conn = sqlite3.connect(str(p))
        assert conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0] == 2
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "reminders" in tables
        conn.close()
        asyncio.run(db.dispose())
