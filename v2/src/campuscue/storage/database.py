"""Owned SQLite database module (M2a).

Responsibilities:
- AsyncEngine + async session factory (SQLAlchemy 2.x + aiosqlite)
- safe schema bootstrap: compatibility check BEFORE any mutation (M2a.1-D)
- owned v1 → v2 migration (M3: adds reminders table)
- dispose

SQLite pragmas: foreign_keys=ON, busy_timeout, WAL for file-backed DB.
Test isolation (M2, hard gate): CAMPUSCUE_ENV=test REQUIRES an explicit
test database path; never silently fall back to the normal DB.

Schema safety contract (M2a.1-D):
  INCOMPATIBLE EXISTING DATABASE -> DETECT -> REFUSE -> ZERO MUTATION
  1. inspect sqlite metadata FIRST (no writes)
  2. schema_meta absent:
       - no application tables at all -> fresh DB -> bootstrap (create + version current)
       - existing unknown tables -> REFUSE (do not claim arbitrary DB files)
  3. schema_meta present:
       - version > supported -> REFUSE without mutation
       - version == supported -> proceed (reopen / verify current tables)
       - version == v1 (supported-1) -> OWNED MIGRATION: create reminders table,
         update version to v2, then proceed (M3; single owned migration path, no Alembic)
       - other older versions -> REFUSE (no arbitrary multi-version chain yet)
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import event, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from campuscue.storage.models import SCHEMA_VERSION, Base, SchemaMeta

_APPLICATION_TABLES = frozenset(
    {"sources", "tasks", "extractions", "provider_configs", "schema_meta", "reminders"}
)

# v1 (M2) schema had no reminders table; v2 (M3) adds it.
_V1_SUPPORTED = 1


@dataclass(frozen=True)
class DatabaseConfig:
    path: str | Path  # e.g. "data/campuscue.db"; ":memory:" not supported for async
    env: str = field(default_factory=lambda: os.environ.get("CAMPUSCUE_ENV", "production"))
    busy_timeout_ms: int = 30000


class SchemaRefusedError(RuntimeError):
    """Existing database is incompatible; nothing was mutated."""


class Database:
    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._enforce_test_isolation(config)
        if str(config.path) in (":memory:", ""):
            raise RuntimeError(":memory: is not supported for the async engine; use a temp file")
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @staticmethod
    def _enforce_test_isolation(config: DatabaseConfig) -> None:
        """M2 hard gate: CAMPUSCUE_ENV=test without an explicit isolated DB path FAILS."""
        if config.env == "test" and str(config.path) in (":memory:", ""):
            raise RuntimeError(
                "CAMPUSCUE_ENV=test requires an explicit isolated test database path "
                "(e.g. pytest tmp_path). Refusing to fall back to the application DB."
            )

    def _url(self) -> str:
        p = str(self._config.path)
        if p == ":memory:":
            raise RuntimeError(":memory: is not supported for the async engine; use a temp file")
        return f"sqlite+aiosqlite:///{p}"

    def _precheck(self) -> tuple[str | None, set[str]]:
        """READ-ONLY preflight on the raw sqlite file. Raises SchemaRefusedError
        for incompatible/unknown databases BEFORE any mutation (M2a.1-D).

        Returns (existing_schema_version | None, user_tables) so initialize()
        can decide: fresh bootstrap / reopen / owned v1->v2 migration.
        """
        path = str(self._config.path)
        if not os.path.exists(path):
            return None, set()
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        except sqlite3.Error as e:
            raise SchemaRefusedError(f"cannot open existing database read-only: {e}") from None
        try:
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            # any table beyond sqlite's own internal tables means this is NOT a fresh file
            user_tables = tables - {"sqlite_sequence", "sqlite_stat1", "sqlite_stat4", "sqlite_master"}
            if "schema_meta" not in tables:
                # legacy/unknown DB without version marker
                if user_tables:
                    raise SchemaRefusedError(
                        f"existing database has tables {sorted(user_tables)} but no "
                        "schema_meta; refusing to claim an arbitrary DB file (migration required)"
                    )
                return None, user_tables  # effectively fresh
            # schema_meta exists: read version FIRST, no writes
            rows = conn.execute("SELECT schema_version FROM schema_meta").fetchall()
            versions = [r[0] for r in rows]
            if not versions:
                raise SchemaRefusedError("schema_meta exists but is empty; refusing to guess")
            unsupported = [v for v in versions if v > SCHEMA_VERSION]
            if unsupported:
                raise SchemaRefusedError(
                    f"unsupported schema version(s) {unsupported!r}; this build supports "
                    f"version {SCHEMA_VERSION}. Refusing to open a newer/unknown database."
                )
            older = [v for v in versions if v < _V1_SUPPORTED]
            if older:
                raise SchemaRefusedError(
                    f"unsupported old schema version(s) {older!r}; no migration chain "
                    f"before v{_V1_SUPPORTED} (requires manual migration)."
                )
            return versions[0], user_tables
        finally:
            conn.close()

    def _migrate_v1_to_v2(self) -> None:
        """Owned migration v1 -> v2 (M3): add reminders table, bump version.

        Runs BEFORE the ORM engine opens, on the raw sqlite file, so the
        migration is explicit and auditable; existing v1 rows are preserved.
        No changes outside adding the reminders table + version bump.
        """
        path = str(self._config.path)
        conn = sqlite3.connect(path)
        try:
            cur = conn.cursor()
            # create reminders table with the same shape as the ORM model (v2)
            cur.executescript(
                """
                CREATE TABLE reminders (
                    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL REFERENCES tasks(id),
                    trigger_at DATETIME NOT NULL,
                    type VARCHAR(16) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    last_run DATETIME,
                    error TEXT,
                    job_id VARCHAR(64),
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                );
                CREATE INDEX ix_reminder_task_id ON reminders (task_id);
                CREATE INDEX ix_reminder_status_trigger ON reminders (status, trigger_at);
                """
            )
            cur.execute("UPDATE schema_meta SET schema_version = ?", (SCHEMA_VERSION,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def initialize(self) -> None:
        """Precheck (zero mutation) -> owned migration if v1 -> engine -> pragmas ->
        create_all -> ensure version row. Reopen of a supported DB is idempotent."""
        version, _tables = self._precheck()
        if version == _V1_SUPPORTED:
            # owned v1 -> v2 migration (M3): BEFORE opening the ORM engine
            self._migrate_v1_to_v2()
        url = self._url()
        self._engine = create_async_engine(url, connect_args={"timeout": self._config.busy_timeout_ms / 1000})

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute(f"PRAGMA busy_timeout={self._config.busy_timeout_ms}")
            if self._config.env != "test":
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # version row (idempotent; precheck already guaranteed compatibility)
        async with self.session() as session:
            row = await session.scalar(select(SchemaMeta).where(SchemaMeta.schema_version == SCHEMA_VERSION))
            if row is None:
                session.add(SchemaMeta(schema_version=SCHEMA_VERSION))
                await session.commit()

    def session(self) -> AsyncSession:
        if self._session_factory is None:
            raise RuntimeError("database not initialized; call initialize() first")
        return self._session_factory()

    @property
    def engine(self) -> AsyncEngine:
        if self._engine is None:
            raise RuntimeError("database not initialized; call initialize() first")
        return self._engine

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None
