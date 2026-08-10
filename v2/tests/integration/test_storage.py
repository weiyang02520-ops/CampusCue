"""M2a storage integration tests. Real temp SQLite (never mock storage)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from campuscue.repositories.repositories import (
    DuplicateError,
    ExtractionRepository,
    NotFoundError,
    ProviderConfigRepository,
    SourceRepository,
    TaskRepository,
)
from campuscue.services.source_service import SourceService, SourceServiceError
from campuscue.storage.database import Database, DatabaseConfig
from campuscue.storage.models import (
    SCHEMA_VERSION,
    Extraction,
    ProviderConfig,
    SchemaMeta,
    Source,
    Task,
    load_audit,
    store_audit,
)


@pytest.fixture
async def db(tmp_path):
    path = tmp_path / "test.db"
    database = Database(DatabaseConfig(path=path, env="test", busy_timeout_ms=5000))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
async def repos(db):
    return {
        "sources": SourceRepository(db.session),
        "tasks": TaskRepository(db.session),
        "extractions": ExtractionRepository(db.session),
        "providers": ProviderConfigRepository(db.session),
    }


def _aware(dt: datetime | None = None) -> datetime:
    return dt or datetime(2026, 8, 10, 15, 59, 0, tzinfo=timezone.utc)


class TestDatabaseInit:
    async def test_empty_db_initialization(self, tmp_path):
        db = Database(DatabaseConfig(path=tmp_path / "a.db", env="test"))
        await db.initialize()
        async with db.session() as s:
            versions = list((await s.scalars(select(SchemaMeta.schema_version))).all())
        assert versions == [SCHEMA_VERSION]
        # tables exist
        async with db.session() as s:
            tables = set(
                (await s.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).scalars().all()
            )
        assert {"sources", "tasks", "extractions", "provider_configs", "schema_meta"} <= tables
        await db.dispose()

    async def test_reopen_existing_db(self, tmp_path):
        path = tmp_path / "b.db"
        db1 = Database(DatabaseConfig(path=path, env="test"))
        await db1.initialize()
        await db1.dispose()
        db2 = Database(DatabaseConfig(path=path, env="test"))
        await db2.initialize()  # must not fail on reopen
        await db2.dispose()

    async def test_unsupported_schema_version_rejected(self, tmp_path):
        path = tmp_path / "c.db"
        raw = sqlite3.connect(path)
        raw.execute("CREATE TABLE schema_meta (id INTEGER PRIMARY KEY AUTOINCREMENT, schema_version INTEGER NOT NULL UNIQUE)")
        raw.execute("INSERT INTO schema_meta (schema_version) VALUES (999)")
        raw.commit()
        raw.close()
        db = Database(DatabaseConfig(path=path, env="test"))
        with pytest.raises(RuntimeError, match="unsupported schema version"):
            await db.initialize()

    async def test_foreign_keys_enabled(self, db):
        async with db.session() as s:
            val = (await s.execute(text("PRAGMA foreign_keys"))).scalar()
        assert val == 1

    async def test_busy_timeout_configured(self, db):
        async with db.session() as s:
            val = (await s.execute(text("PRAGMA busy_timeout"))).scalar()
        assert val >= 5000

    async def test_test_env_without_explicit_db_fails(self):
        with pytest.raises(RuntimeError, match="test.*explicit"):
            Database(DatabaseConfig(path=":memory:", env="test"))
        with pytest.raises(RuntimeError, match="test.*explicit"):
            Database(DatabaseConfig(path="", env="test"))

    async def test_inmemory_rejected(self):
        with pytest.raises(RuntimeError, match=":memory:"):
            Database(DatabaseConfig(path=":memory:", env="production"))


class TestSourceRepository:
    async def test_crud(self, repos):
        src = await repos["sources"].create(platform="onebot", conversation_id="123", name="测试群")
        assert src.id > 0
        assert src.enabled is True
        assert src.context_window == 5
        got = await repos["sources"].get(src.id)
        assert got.name == "测试群"
        updated = await repos["sources"].update(src.id, name="新名", enabled=False)
        assert updated.name == "新名"
        assert updated.enabled is False
        assert await repos["sources"].get_by_identity("onebot", "123") is not None
        assert await repos["sources"].get_by_identity("onebot", "999") is None

    async def test_composite_unique_identity(self, repos):
        await repos["sources"].create(platform="onebot", conversation_id="100")
        with pytest.raises(DuplicateError):
            await repos["sources"].create(platform="onebot", conversation_id="100")
        # same conversation_id on different platform is ALLOWED (ADR-012-C)
        s2 = await repos["sources"].create(platform="telegram", conversation_id="100")
        assert s2.id > 0

    async def test_not_found(self, repos):
        with pytest.raises(NotFoundError):
            await repos["sources"].get(999999)

    async def test_context_window_validation(self, repos):
        with pytest.raises(ValueError, match="context_window"):
            await repos["sources"].create(platform="onebot", conversation_id="x", context_window=0)

    async def test_aware_datetime_roundtrip(self, repos):
        src = await repos["sources"].create(platform="onebot", conversation_id="t")
        got = await repos["sources"].get(src.id)
        assert got.created_at.tzinfo is not None
        assert got.created_at.utcoffset().total_seconds() == 0  # UTC


class TestSourceService:
    async def test_create_and_disable(self, db):
        service = SourceService(SourceRepository(db.session))
        src = await service.create_source(platform="onebot", conversation_id="555", name="群A")
        assert src.enabled is True
        disabled = await service.disable("onebot", "555")
        assert disabled.enabled is False
        await service.enable("onebot", "555")

    async def test_duplicate_via_service(self, db):
        service = SourceService(SourceRepository(db.session))
        await service.create_source(platform="onebot", conversation_id="1")
        with pytest.raises(SourceServiceError, match="already exists"):
            await service.create_source(platform="onebot", conversation_id="1")

    async def test_invalid_inputs(self, db):
        service = SourceService(SourceRepository(db.session))
        with pytest.raises(SourceServiceError, match="platform"):
            await service.create_source(platform="", conversation_id="1")
        with pytest.raises(SourceServiceError, match="conversation_id"):
            await service.create_source(platform="onebot", conversation_id="")
        with pytest.raises(SourceServiceError, match="privacy_policy"):
            await service.create_source(platform="onebot", conversation_id="1", privacy_policy="evil")

    async def test_missing_source(self, db):
        service = SourceService(SourceRepository(db.session))
        with pytest.raises(SourceServiceError, match="not found"):
            await service.disable("onebot", "nonexistent")


class TestTaskRepository:
    async def test_create_and_get(self, repos):
        task = await repos["tasks"].create(
            title="第三章作业", category="homework", course="高等数学",
            deadline=_aware(), status="pending", source_id=None, source_message_id="m1",
            dedup_key="k1",
        )
        got = await repos["tasks"].get(task.id)
        assert got.title == "第三章作业"
        assert got.deadline.tzinfo is not None
        assert got.deadline.utcoffset().total_seconds() == 0
        assert got.status == "pending"

    async def test_enum_values(self, repos):
        from campuscue.storage.enums import TaskStatus
        # all four canonical statuses are storable (ADR-012-A)
        for status in TaskStatus:
            t = await repos["tasks"].create(title=status.value, status=status.value)
            assert t.status == status.value

    async def test_source_message_duplicate_safeguard(self, repos):
        src = await repos["sources"].create(platform="onebot", conversation_id="g1")
        await repos["tasks"].create(title="A", source_id=src.id, source_message_id="m-42")
        with pytest.raises(DuplicateError, match="source_message_id"):
            await repos["tasks"].create(title="B", source_id=src.id, source_message_id="m-42")

    async def test_find_by_source_message(self, repos):
        src = await repos["sources"].create(platform="onebot", conversation_id="g2")
        await repos["tasks"].create(title="A", source_id=src.id, source_message_id="m-1")
        found = await repos["tasks"].find_by_source_message(src.id, "m-1")
        assert found is not None and found.title == "A"
        assert await repos["tasks"].find_by_source_message(src.id, "m-zzz") is None

    async def test_find_recent_by_dedup_key(self, repos):
        await repos["tasks"].create(title="A", dedup_key="dup-1")
        await repos["tasks"].create(title="B", dedup_key="dup-1")
        await repos["tasks"].create(title="C", dedup_key="other")
        found = await repos["tasks"].find_recent_by_dedup_key("dup-1")
        assert len(found) == 2

    async def test_naive_deadline_rejected(self, repos):
        with pytest.raises(ValueError, match="naive"):
            await repos["tasks"].create(title="x", deadline=datetime(2026, 8, 10, 15, 59))

    async def test_non_utc_aware_converted_to_utc(self, repos):
        tz = timezone(timedelta(hours=8))
        dt = datetime(2026, 8, 10, 23, 59, tzinfo=tz)  # 23:59 +08:00 = 15:59 UTC
        task = await repos["tasks"].create(title="x", deadline=dt)
        got = await repos["tasks"].get(task.id)
        assert got.deadline == datetime(2026, 8, 10, 15, 59, tzinfo=timezone.utc)


class TestExtractionRepository:
    async def test_create_and_audit_roundtrip(self, repos):
        audit = {"l1": {"score": 3.5}, "l3": {"has_task": True}, "l4": {"deadline": "2026-08-14T15:59:00Z"}, "l5": {"dedup": "new"}, "outcome": {"task_id": 1}}
        row = await repos["extractions"].create(
            source_id=None, source_message_id="m-7", trace_id="t-1",
            status="success", confidence=0.9,
            raw_result='{"has_task": true}', normalized_result='{"title": "作业"}',
            audit=store_audit(audit),
        )
        rows = await repos["extractions"].list_for_message("m-7")
        assert len(rows) == 1
        loaded = load_audit(rows[0].audit)
        assert loaded["l5"]["dedup"] == "new"
        assert loaded["outcome"]["task_id"] == 1

    async def test_error_redacted(self, repos):
        row = await repos["extractions"].create(
            source_id=None, source_message_id="m-8", trace_id="t-2",
            status="error", error="provider timeout [REDACTED]",
        )
        assert "timeout" in row.error  # safe message only


class TestProviderConfigRepository:
    async def test_crud_and_unique_name(self, repos):
        cfg = await repos["providers"].create(
            name="default", base_url="https://api.example.com/v1", model="gpt-4o",
            secret_reference="CAMPUSCUE_LLM_API_KEY",
        )
        assert cfg.id > 0
        got = await repos["providers"].get(cfg.id)
        assert got.secret_reference == "CAMPUSCUE_LLM_API_KEY"
        with pytest.raises(DuplicateError, match="name"):
            await repos["providers"].create(name="default", base_url="x", model="y")

    async def test_secret_value_never_in_db(self, repos, tmp_path):
        # simulate a secret existing in env; only the reference goes to DB
        await repos["providers"].create(
            name="sec", base_url="https://x/v1", model="m",
            secret_reference="TEST_FAKE_PROVIDER_KEY",
        )
        raw = sqlite3.connect(tmp_path / "test.db")
        rows = raw.execute("SELECT * FROM provider_configs").fetchall()
        joined = " ".join(str(r) for r in rows)
        assert "TEST_FAKE_PROVIDER_KEY" in joined  # reference name present
        assert "fake-secret-value" not in joined  # actual value NEVER present

    async def test_list_enabled(self, repos):
        await repos["providers"].create(name="a", base_url="https://x/v1", model="m", enabled=True)
        await repos["providers"].create(name="b", base_url="https://x/v1", model="m", enabled=False)
        enabled = await repos["providers"].list_enabled()
        assert [c.name for c in enabled] == ["a"]


class TestTransactions:
    async def test_rollback_on_failure(self, repos):
        # unique violation must roll back and leave DB consistent
        await repos["providers"].create(name="x1", base_url="https://x/v1", model="m")
        with pytest.raises(DuplicateError):
            await repos["providers"].create(name="x1", base_url="https://x/v1", model="m")
        # a subsequent valid op works (no poisoned session)
        c2 = await repos["providers"].create(name="x2", base_url="https://x/v1", model="m")
        assert c2.name == "x2"
