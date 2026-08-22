"""POST-M7 P1A disposable storage and recovery fault-injection tests.

Every scenario snapshots canonical rows before and after the injected fault.
These tests deliberately use the real repositories/services with temporary
SQLite files; they do not exercise production data or real integrations.
"""

from __future__ import annotations

import copy
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from campuscue.storage.models import (
    Extraction,
    ProviderConfig,
    Reminder,
    Setting,
    Source,
    Task,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 22, 4, 0, tzinfo=UTC)


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    path = tmp_path / "p1a-storage.db"
    database = Database(DatabaseConfig(path=path, env="test", busy_timeout_ms=50))
    await database.initialize()
    yield database, path
    await database.dispose()


async def _snapshot(db) -> dict[str, list[tuple]]:
    """Stable logical snapshot for the rows involved in P1A decisions."""

    def value(raw):
        if isinstance(raw, datetime):
            return raw.astimezone(UTC).isoformat()
        return raw

    result: dict[str, list[tuple]] = {}
    async with db.session() as session:
        for model in (Source, Task, Extraction, Reminder, ProviderConfig, Setting):
            rows = (await session.scalars(select(model))).all()
            result[model.__tablename__] = [
                tuple(value(getattr(row, column.name)) for column in model.__table__.columns)
                for row in sorted(rows, key=lambda row: str(getattr(row, model.__table__.primary_key.columns.values()[0].name)))
            ]
    return result


async def _task_repo(db):
    from campuscue.repositories.repositories import TaskRepository

    return TaskRepository(db.session)


async def _reminder_repo(db):
    from campuscue.repositories.repositories import ReminderRepository

    return ReminderRepository(db.session)


async def _seed_task(db, *, deadline: datetime | None = None):
    repo = await _task_repo(db)
    return await repo.create(
        title="P1A seed task",
        category="homework",
        course="高等数学",
        deadline=deadline,
        source_id=None,
        source_message_id=None,
    )


def _hold_immediate_lock(path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), timeout=0.05)
    connection.execute("BEGIN IMMEDIATE")
    return connection


@pytest.mark.asyncio
async def test_stability_r_a07_task_create_lock_failure_has_no_half_row(db):
    database, path = db
    repo = await _task_repo(database)
    before = await _snapshot(database)
    lock = _hold_immediate_lock(path)
    try:
        with pytest.raises(OperationalError):
            await repo.create(title="locked task", category="homework")
    finally:
        lock.rollback()
        lock.close()
    assert await _snapshot(database) == before
    recovered = await repo.create(title="after lock", category="homework")
    assert recovered.title == "after lock"


@pytest.mark.asyncio
async def test_stability_r_a07_extraction_and_reminder_lock_fail_without_orphans(db):
    database, path = db
    from campuscue.repositories.repositories import ExtractionRepository

    task = await _seed_task(database, deadline=NOW + timedelta(days=3))
    before = await _snapshot(database)
    lock = _hold_immediate_lock(path)
    try:
        with pytest.raises(OperationalError):
            await ExtractionRepository(database.session).create(
                source_id=None, source_message_id="locked-message", trace_id="locked-trace"
            )
        with pytest.raises(OperationalError):
            await (await _reminder_repo(database)).create(
                task_id=task.id, trigger_at=NOW + timedelta(days=1), type="deadline"
            )
    finally:
        lock.rollback()
        lock.close()
    assert await _snapshot(database) == before
    reminder = await (await _reminder_repo(database)).create(
        task_id=task.id, trigger_at=NOW + timedelta(days=1), type="deadline"
    )
    assert reminder.task_id == task.id


@pytest.mark.asyncio
async def test_stability_r_a07_task_mutation_lock_failure_has_no_partial_update(db):
    database, path = db
    repo = await _task_repo(database)
    task = await _seed_task(database)
    before = await _snapshot(database)
    lock = _hold_immediate_lock(path)
    try:
        with pytest.raises(OperationalError):
            await repo.update_fields(task.id, title="should not commit")
    finally:
        lock.rollback()
        lock.close()
    assert await _snapshot(database) == before
    updated = await repo.update_fields(task.id, title="after lock")
    assert updated.title == "after lock"


@pytest.mark.asyncio
async def test_stability_r_a07_commit_failure_rolls_back_and_session_recovers(db, monkeypatch):
    database, _ = db
    repo = await _task_repo(database)
    before = await _snapshot(database)
    original_commit = AsyncSession.commit
    state = {"fail": True}

    async def fail_once(session):
        if state["fail"]:
            state["fail"] = False
            raise RuntimeError("injected commit failure")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", fail_once)
    with pytest.raises(RuntimeError, match="injected commit failure"):
        await repo.create(title="commit failure", category="homework")
    assert await _snapshot(database) == before

    monkeypatch.setattr(AsyncSession, "commit", original_commit)
    recovered = await repo.create(title="next operation", category="homework")
    assert recovered.title == "next operation"


async def _recovery_env(path):
    from campuscue.repositories.repositories import ReminderRepository, TaskRepository
    from campuscue.services.reminder_service import ReminderService
    from campuscue.storage.clock import FixedClock
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.tasks.reminder_policy import ReminderPolicy

    database = Database(DatabaseConfig(path=path, env="test", busy_timeout_ms=100))
    await database.initialize()
    clock = FixedClock(NOW)
    tasks = TaskRepository(database.session, clock=clock)
    reminders = ReminderRepository(database.session, clock=clock)

    class Scheduler:
        def __init__(self, fail_after: int | None = None):
            self.jobs: dict[str, int] = {}
            self.calls = 0
            self.fail_after = fail_after

        async def schedule(self, *, job_id, run_at, reminder_id):
            self.calls += 1
            if self.fail_after is not None and self.calls > self.fail_after:
                raise RuntimeError("injected scheduler failure")
            self.jobs[job_id] = reminder_id

        async def unschedule(self, job_id):
            self.jobs.pop(job_id, None)

        async def clear_all(self):
            self.jobs.clear()

    scheduler = Scheduler()
    service = ReminderService(
        reminders,
        tasks,
        scheduler=scheduler,
        clock=clock,
        timezone=ZoneInfo("Asia/Shanghai"),
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    return database, tasks, reminders, service, scheduler


async def _restart_and_resync(path):
    database, tasks, reminders, service, scheduler = await _recovery_env(path)
    installed = await service.resync_all()
    facts = await reminders.list_scheduled()
    task_rows = await tasks.list_all()
    await database.dispose()
    return installed, facts, task_rows, scheduler.jobs


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["before_plan", "partial_fact", "scheduler"])
async def test_stability_r_a08_task_reminder_faults_converge_after_restart(db, fault, monkeypatch):
    database, path = db
    await database.dispose()
    database2, tasks, reminders, service, scheduler = await _recovery_env(path)
    try:
        from campuscue.services.task_service import TaskService

        task_service = TaskService(tasks, reminder_service=service)
        if fault == "before_plan":
            async def fail_before(task):
                raise RuntimeError("injected before plan")

            monkeypatch.setattr(service, "plan_reminders", fail_before)
        elif fault == "partial_fact":
            original_create = reminders.create
            state = {"calls": 0}

            async def fail_after_one(**kwargs):
                state["calls"] += 1
                if state["calls"] > 1:
                    raise RuntimeError("injected partial fact failure")
                return await original_create(**kwargs)

            monkeypatch.setattr(reminders, "create", fail_after_one)
        else:
            scheduler.fail_after = 1

        with pytest.raises(RuntimeError):
            await task_service.create_manual_task(
                title=f"crash-gap-{fault}",
                category="homework",
                course="高等数学",
                deadline=NOW + timedelta(days=3),
            )
    finally:
        await database2.dispose()

    installed, facts, task_rows, jobs = await _restart_and_resync(path)
    assert len(task_rows) == 1
    assert task_rows[0].title == f"crash-gap-{fault}"
    assert len(facts) == 3
    assert len(jobs) == 3
    assert installed == 3


@pytest.mark.asyncio
async def test_stability_r_a08_existing_reminder_cancel_gap_converges(db, monkeypatch):
    database, path = db
    await database.dispose()
    database2, tasks, reminders, service, _ = await _recovery_env(path)
    try:
        from campuscue.services.task_service import TaskService

        task_service = TaskService(tasks, reminder_service=service)
        task = await task_service.create_manual_task(
            title="old plan", category="homework", deadline=NOW + timedelta(days=3)
        )
        original_cancel = reminders.cancel_for_task

        async def cancel_then_fail(task_id, *, now=None):
            result = await original_cancel(task_id, now=now)
            raise RuntimeError("injected after old reminder cancel")

        monkeypatch.setattr(reminders, "cancel_for_task", cancel_then_fail)
        with pytest.raises(RuntimeError):
            await task_service.change_deadline(task.id, NOW + timedelta(days=4))
    finally:
        await database2.dispose()

    installed, facts, task_rows, jobs = await _restart_and_resync(path)
    assert task_rows[0].deadline == NOW + timedelta(days=4)
    assert len(facts) == 3
    assert len(jobs) == 3
    assert installed == 3


async def _system_env(path):
    from campuscue.repositories.repositories import ReminderRepository, TaskRepository
    from campuscue.services.reminder_service import ReminderService
    from campuscue.services.system_service import SystemService
    from campuscue.services.task_service import TaskService
    from campuscue.storage.clock import FixedClock
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=path, env="test", busy_timeout_ms=100))
    await database.initialize()
    clock = FixedClock(NOW)
    tasks = TaskRepository(database.session, clock=clock)
    reminders = ReminderRepository(database.session, clock=clock)
    reminder_service = ReminderService(
        reminders, tasks, clock=clock, timezone=ZoneInfo("Asia/Shanghai")
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)
    system = SystemService(database.session, task_service, reminder_service=reminder_service)
    return database, tasks, reminders, task_service, system


async def _canonical_backup_state(database):
    return await _snapshot(database)


@pytest.mark.asyncio
async def test_stability_r_a18_restore_failures_preserve_canonical_state(db, monkeypatch):
    database, path = db
    await database.dispose()
    database2, tasks, reminders, task_service, system = await _system_env(path)
    try:
        from campuscue.repositories.repositories import SourceRepository

        source = await SourceRepository(database2.session).create(
            platform="onebot", conversation_id="90123", name="P1A source"
        )
        task = await task_service.create_manual_task(
            title="restore baseline", category="homework", source_id=source.id,
            deadline=NOW + timedelta(days=3),
        )
        backup = await system.create_backup()
        before = await _canonical_backup_state(database2)

        malformed = {"format_version": 1}
        with pytest.raises(ValueError):
            await system.restore(malformed, confirm_replace=True)
        assert await _canonical_backup_state(database2) == before

        variants = []
        invalid_type = copy.deepcopy(backup)
        invalid_type["data"]["tasks"][0]["deadline"] = {"invalid": True}
        variants.append(invalid_type)
        invalid_fk = copy.deepcopy(backup)
        invalid_fk["data"]["tasks"][0]["source_id"] = 999999
        variants.append(invalid_fk)
        duplicate_key = copy.deepcopy(backup)
        duplicate_key["data"]["sources"].append(copy.deepcopy(duplicate_key["data"]["sources"][0]))
        variants.append(duplicate_key)
        missing_column = copy.deepcopy(backup)
        del missing_column["data"]["tasks"][0]["title"]
        variants.append(missing_column)

        for variant in variants:
            with pytest.raises(Exception):
                await system.restore(variant, confirm_replace=True)
            assert await _canonical_backup_state(database2) == before

        original_commit = AsyncSession.commit
        state = {"fail": True}

        async def fail_restore_commit(session):
            if state["fail"]:
                state["fail"] = False
                raise RuntimeError("injected restore commit failure")
            await original_commit(session)

        monkeypatch.setattr(AsyncSession, "commit", fail_restore_commit)
        with pytest.raises(RuntimeError, match="injected restore commit failure"):
            await system.restore(copy.deepcopy(backup), confirm_replace=True)
        assert await _canonical_backup_state(database2) == before
    finally:
        await database2.dispose()


@pytest.mark.asyncio
async def test_stability_r_a18_successful_restore_replaces_and_resyncs_only_after_commit(db):
    database, path = db
    await database.dispose()
    database2, tasks, reminders, task_service, system = await _system_env(path)
    try:
        from campuscue.repositories.repositories import SourceRepository

        source = await SourceRepository(database2.session).create(
            platform="onebot", conversation_id="90124", name="P1A restore"
        )
        await task_service.create_manual_task(
            title="restore source fact", category="homework", source_id=source.id,
            deadline=NOW + timedelta(days=3),
        )
        backup = await system.create_backup()
        await task_service.create_manual_task(title="temporary", category="other")
        result = await system.restore(copy.deepcopy(backup), confirm_replace=True)
        assert result == {"restored": True, "schema_version": 3}
        rows = await tasks.list_all()
        assert [row.title for row in rows] == ["restore source fact"]
        scheduled = await reminders.list_scheduled()
        assert len(scheduled) == 3
    finally:
        await database2.dispose()
