"""M3.4 Storage Safety Final Seal regression tests (external review round).

A. v1 -> v2 migration is ONE explicit transaction (BEGIN IMMEDIATE ...
   COMMIT / ROLLBACK) — forced mid-migration failure leaves NO partial
   schema; schema_version stays 1.
B. schema_meta=1 + M3-only structures (reminders) -> REFUSE (half-migrated).
C. version-specific schema manifests cover the COMPLETE ORM column contract
   (not a subset): missing any ORM-required column -> REFUSE, zero mutation.
"""

from __future__ import annotations

import asyncio
import sqlite3

import pytest

from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

# Full valid v1 DDL matching the owned M2/v1 schema (all ORM columns).
_V1_DDL = """
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
"""

_V2_REMINDERS_DDL = """
CREATE TABLE reminders (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    trigger_at DATETIME NOT NULL, type VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL, last_run DATETIME, error TEXT,
    job_id VARCHAR(64), created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CHECK (type IN ('day_before','hours_before','deadline')),
    CHECK (status IN ('scheduled','fired','cancelled'))
);
"""


def _make_v1(path, *, reminders=False, extra_index=False):
    conn = sqlite3.connect(str(path))
    conn.executescript(_V1_DDL)
    if extra_index:
        # pre-existing index that collides with the migration's new index name
        conn.execute("CREATE INDEX ix_reminder_task_id ON extractions (source_id)")
    if reminders:
        conn.executescript(_V2_REMINDERS_DDL)
    conn.execute("INSERT INTO schema_meta (schema_version) VALUES (1)")
    conn.commit()
    conn.close()


def _tables(path):
    conn = sqlite3.connect(str(path))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    return tables


def _indexes(path):
    conn = sqlite3.connect(str(path))
    idx = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    conn.close()
    return idx


def _version(path):
    conn = sqlite3.connect(str(path))
    v = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
    conn.close()
    return v


# ------------------------------------------------------------------ A: atomic migration

class TestAtomicMigration:
    def test_forced_mid_migration_failure_rolls_back_completely(self, tmp_path):
        """CREATE TABLE reminders succeeds, then CREATE INDEX fails
        (conflicting pre-existing index name) -> whole migration rolls back:
        schema_version stays 1, no reminders table, no reminder indexes,
        original v1 tables/data intact."""
        p = tmp_path / "atomic.db"
        _make_v1(p, extra_index=True)  # ix_reminder_task_id already exists
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(Exception):  # sqlite3.OperationalError
            asyncio.run(db.initialize())
        assert _version(p) == 1  # version NOT bumped
        tables = _tables(p)
        assert "reminders" not in tables  # no partial reminders schema
        idx = _indexes(p)
        assert "ix_reminder_status_trigger" not in idx
        # original v1 tables intact
        for t in ("sources", "tasks", "extractions", "provider_configs", "schema_meta"):
            assert t in tables

    def test_clean_v1_still_migrates_after_failure_condition_removed(self, tmp_path):
        """Same procedure, clean v1 (no conflicting index) -> migration succeeds."""
        p = tmp_path / "clean.db"
        _make_v1(p)
        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())
        assert _version(p) == 2
        assert "reminders" in _tables(p)
        asyncio.run(db.dispose())


# ------------------------------------------------------------------ B: half-migrated v1

class TestHalfMigratedV1:
    def test_schema_meta_1_with_reminders_refused_zero_mutation(self, tmp_path):
        """schema_meta=1 + reminders already present -> REFUSE, ZERO FURTHER
        MUTATION (never guess whether a partial migration is safe)."""
        p = tmp_path / "half.db"
        _make_v1(p, reminders=True)
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="half-migrated|reminders"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before  # byte-identical


# ------------------------------------------------------------------ C: complete column manifests

class TestCompleteColumnManifests:
    def _v2_without(self, path, *, drop_col=None, drop_table=None):
        """Build a v2-shaped DB, optionally dropping one column/table."""
        conn = sqlite3.connect(str(path))
        conn.executescript(_V1_DDL)
        conn.executescript(_V2_REMINDERS_DDL)
        if drop_table:
            conn.execute(f"DROP TABLE {drop_table}")
        if drop_col:
            # rebuild tasks table without the dropped column via copy
            if drop_col in ("source_message_id",):
                conn.executescript(
                    """
                    ALTER TABLE tasks RENAME TO tasks_old;
                    CREATE TABLE tasks (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        title VARCHAR(256) NOT NULL, description TEXT,
                        category VARCHAR(32) NOT NULL, course VARCHAR(128),
                        deadline DATETIME, status VARCHAR(32) NOT NULL,
                        priority VARCHAR(16) NOT NULL, confidence FLOAT,
                        dedup_key VARCHAR(128), source_id INTEGER,
                        source_text_reference TEXT,
                        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                    );
                    DROP TABLE tasks_old;
                    """
                )
            elif drop_col == "job_id":
                conn.executescript(
                    """
                    ALTER TABLE reminders RENAME TO reminders_old;
                    CREATE TABLE reminders (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        task_id INTEGER NOT NULL REFERENCES tasks(id),
                        trigger_at DATETIME NOT NULL, type VARCHAR(16) NOT NULL,
                        status VARCHAR(16) NOT NULL, last_run DATETIME, error TEXT,
                        created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL
                    );
                    DROP TABLE reminders_old;
                    """
                )
            elif drop_col == "timeout_s":
                conn.executescript(
                    """
                    ALTER TABLE provider_configs RENAME TO provider_configs_old;
                    CREATE TABLE provider_configs (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(64) NOT NULL, provider_type VARCHAR(32) NOT NULL,
                        base_url VARCHAR(256) NOT NULL, model VARCHAR(128) NOT NULL,
                        temperature FLOAT, max_tokens INTEGER, max_context_tokens INTEGER,
                        secret_reference VARCHAR(128),
                        enabled BOOLEAN NOT NULL, created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL
                    );
                    DROP TABLE provider_configs_old;
                    """
                )
            else:
                raise AssertionError(f"unhandled drop_col {drop_col}")
        conn.execute("INSERT INTO schema_meta (schema_version) VALUES (2)")
        conn.commit()
        conn.close()

    def test_v2_tasks_missing_source_message_id_refused(self, tmp_path):
        p = tmp_path / "t.db"
        self._v2_without(p, drop_col="source_message_id")
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="source_message_id"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_v2_reminders_missing_job_id_refused(self, tmp_path):
        p = tmp_path / "r.db"
        self._v2_without(p, drop_col="job_id")
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="job_id"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_v2_provider_configs_missing_timeout_s_refused(self, tmp_path):
        p = tmp_path / "pc.db"
        self._v2_without(p, drop_col="timeout_s")
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="timeout_s"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_v1_tasks_missing_created_at_refused_zero_mutation(self, tmp_path):
        """v1 with a truncated tasks table (missing a canonical ORM column)
        -> REFUSE zero mutation (subset-of-columns no longer accepted)."""
        p = tmp_path / "v1trunc.db"
        conn = sqlite3.connect(str(p))
        conn.executescript(_V1_DDL)
        conn.executescript(
            """
            ALTER TABLE tasks RENAME TO tasks_old;
            CREATE TABLE tasks (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                title VARCHAR(256) NOT NULL, category VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL, priority VARCHAR(16) NOT NULL
            );
            DROP TABLE tasks_old;
            """
        )
        conn.execute("INSERT INTO schema_meta (schema_version) VALUES (1)")
        conn.commit()
        conn.close()
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="missing required column"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_valid_v1_migrates_and_valid_v2_reopens(self, tmp_path):
        """Complete manifests: full valid v1 -> migrate PASS; full valid v2 ->
        reopen PASS (no mutation)."""
        p = tmp_path / "full.db"
        _make_v1(p)
        db = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db.initialize())
        assert _version(p) == 2
        assert "reminders" in _tables(p)
        # reopen the migrated v2 (idempotent)
        db2 = Database(DatabaseConfig(path=p, env="test"))
        asyncio.run(db2.initialize())  # must not raise
        assert _version(p) == 2
        asyncio.run(db.dispose())
        asyncio.run(db2.dispose())
