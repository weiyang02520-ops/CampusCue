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
    {"sources", "tasks", "extractions", "provider_configs", "schema_meta", "reminders", "settings"}
)

# v1 (M2) schema had no reminders table; v2 (M3) adds it; v3 (M5) adds settings
# + sources.deleted_at + M5 indexes.
_V1_SUPPORTED = 1
_V2_SUPPORTED = 2


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
            # schema_meta exists: read version FIRST, no writes.
            # M3.2-B: schema_meta cardinality is a GLOBAL database identity
            # invariant — exactly one version row must be validated BEFORE any
            # version dispatch (v1/v2/future alike). Never rely on SELECT row
            # order: [1,2] and [2,1] both REFUSE with ZERO MUTATION.
            rows = conn.execute("SELECT schema_version FROM schema_meta").fetchall()
            if len(rows) != 1:
                raise SchemaRefusedError(
                    f"schema_meta has {len(rows)} version row(s); exactly one "
                    "coherent version row is required"
                )
            versions = [r[0] for r in rows]
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
            version = versions[0]
            # M3.3-B: an existing CURRENT-version database must be structurally
            # validated READ-ONLY before create_all may touch it. A schema_meta
            # version marker alone does not prove the application structure is
            # intact (missing tables/columns must REFUSE, not be auto-repaired).
            if version == SCHEMA_VERSION:
                Database._validate_application_schema(
                    conn, user_tables,
                    version=version,
                    required_tables=Database._V3_REQUIRED_TABLES,
                    required_columns=Database._V3_REQUIRED_COLUMNS,
                    refuse_prefix="refusing to open:",
                )
            return version, user_tables
        finally:
            conn.close()

    @staticmethod
    def _validate_application_schema(
        conn: sqlite3.Connection,
        tables: set[str],
        *,
        version: int,
        required_tables: set[str],
        required_columns: dict[str, set[str]],
        refuse_prefix: str,
    ) -> None:
        """Shared structural validator: required tables + critical columns.
        Read-only; SchemaRefusedError = ZERO MUTATION."""
        missing_tables = required_tables - tables
        if missing_tables:
            raise SchemaRefusedError(
                f"{refuse_prefix} malformed schema v{version} database missing "
                f"table(s) {sorted(missing_tables)}"
            )
        for table, cols in required_columns.items():
            if table not in tables:
                continue
            actual = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            missing_cols = cols - actual
            if missing_cols:
                raise SchemaRefusedError(
                    f"{refuse_prefix} table {table!r} missing required column(s) "
                    f"{sorted(missing_cols)} (malformed schema v{version})"
                )

    # ---- canonical version-specific schema manifests (M3.4-B) --------------
    # COMPLETE column contract for every owned application table per version —
    # NOT a subset of "critical" columns: every column the ORM/runtime expects
    # must exist before the DB is opened as that version. Extra columns are
    # tolerated; missing ones REFUSE with zero mutation.
    # (sources/extractions columns are identical across v1/v2)

    _COMMON_TABLE_COLUMNS: dict[str, set[str]] = {
        "sources": {
            "id", "platform", "conversation_id", "name", "enabled", "auto_extract",
            "context_window", "privacy_policy", "created_at", "updated_at",
        },
        "tasks": {
            "id", "title", "description", "category", "course", "deadline",
            "status", "priority", "confidence", "dedup_key", "source_id",
            "source_message_id", "source_text_reference", "created_at", "updated_at",
        },
        "extractions": {
            "id", "source_id", "source_message_id", "trace_id", "provider", "model",
            "status", "confidence", "raw_result", "normalized_result", "audit",
            "error", "created_at",
        },
        "provider_configs": {
            "id", "name", "provider_type", "base_url", "model", "temperature",
            "max_tokens", "max_context_tokens", "timeout_s", "secret_reference",
            "enabled", "created_at", "updated_at",
        },
    }
    _REMINDER_COLUMNS = {
        "id", "task_id", "trigger_at", "type", "status", "last_run", "error",
        "job_id", "created_at", "updated_at",
    }

    # v1 (M2) schema: no reminders table; complete v1 column contract
    _V1_REQUIRED_TABLES = frozenset(
        {"sources", "tasks", "extractions", "provider_configs", "schema_meta"}
    )
    _V1_REQUIRED_COLUMNS = dict(_COMMON_TABLE_COLUMNS)

    # v2 (M3) schema: + reminders table (complete ORM contract)
    _V2_REQUIRED_TABLES = frozenset(
        {"sources", "tasks", "extractions", "provider_configs", "reminders", "schema_meta"}
    )
    _V2_REQUIRED_COLUMNS = dict(_COMMON_TABLE_COLUMNS)
    _V2_REQUIRED_COLUMNS["reminders"] = _REMINDER_COLUMNS

    _SETTINGS_COLUMNS = {"key", "value", "updated_at"}
    _V3_REQUIRED_TABLES = frozenset(_V2_REQUIRED_TABLES | {"settings"})
    _V3_REQUIRED_COLUMNS = dict(_COMMON_TABLE_COLUMNS)
    _V3_REQUIRED_COLUMNS["sources"] = set(_COMMON_TABLE_COLUMNS["sources"]) | {"deleted_at"}
    _V3_REQUIRED_COLUMNS["reminders"] = _REMINDER_COLUMNS
    _V3_REQUIRED_COLUMNS["settings"] = _SETTINGS_COLUMNS

    @staticmethod
    def _validate_v1_schema(conn: sqlite3.Connection, tables: set[str]) -> None:
        """M3.1-D/3.4: prove a schema_meta=1 database is a VALID CampusCue v1
        schema BEFORE mutation. Distinguishes VALID V1 from MALFORMED/ARBITRARY
        SQLite that merely carries schema_meta=1.

        - required application tables present (COMPLETE v1 column contract)
        - NO M3-only structures (reminders table) — a schema_meta=1 database
          that already contains reminders is a HALF-MIGRATED/partial state:
          REFUSE with ZERO FURTHER MUTATION (never guess/recover)
        - schema_meta has EXACTLY ONE coherent version row
        If malformed -> SchemaRefusedError, ZERO MUTATION (nothing written yet).
        """
        # M3.4-A2: half-migrated v1 (already contains M3-only structures) ->
        # refuse; do not guess whether a partially migrated DB is safe
        if "reminders" in tables:
            raise SchemaRefusedError(
                "refusing to migrate: schema_meta=1 database already contains "
                "M3-only structure 'reminders' (half-migrated/partial state); "
                "refusing to guess — manual inspection required"
            )
        Database._validate_application_schema(
            conn, tables,
            version=1,
            required_tables=Database._V1_REQUIRED_TABLES,
            required_columns=Database._V1_REQUIRED_COLUMNS,
            refuse_prefix="refusing to migrate:",
        )
        # schema_meta exactly one coherent row — also enforced globally in
        # _precheck (M3.2-B) before version dispatch; kept here as defense
        rows = conn.execute("SELECT schema_version FROM schema_meta").fetchall()
        if len(rows) != 1:
            raise SchemaRefusedError(
                f"refusing to migrate: schema_meta has {len(rows)} version row(s); "
                "exactly one coherent version required"
            )

    @staticmethod
    def _validate_v2_schema(conn: sqlite3.Connection, tables: set[str]) -> None:
        """Prove a schema_meta=2 database is a VALID CampusCue v2 schema BEFORE
        migration. Refuse if it already contains M5-only structures (settings or
        sources.deleted_at) — that is a half-migrated/partial state."""
        if "settings" in tables:
            raise SchemaRefusedError(
                "refusing to migrate: schema_meta=2 database already contains "
                "M5-only structure 'settings' (half-migrated/partial state); "
                "refusing to guess — manual inspection required"
            )
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)").fetchall()}
        if "deleted_at" in cols:
            raise SchemaRefusedError(
                "refusing to migrate: schema_meta=2 database already contains "
                "M5-only column 'sources.deleted_at' (half-migrated/partial state); "
                "refusing to guess — manual inspection required"
            )
        Database._validate_application_schema(
            conn, tables,
            version=2,
            required_tables=Database._V2_REQUIRED_TABLES,
            required_columns=Database._V2_REQUIRED_COLUMNS,
            refuse_prefix="refusing to migrate:",
        )

    def _migrate_v1_to_v2(self) -> None:
        """Owned migration v1 -> v2 (M3): add reminders table, bump version.

        Runs BEFORE the ORM engine opens, on the raw sqlite file, so the
        migration is explicit and auditable; existing v1 rows are preserved.

        M3.4-A ATOMICITY: all migration DDL + the schema-version bump execute
        inside ONE explicit SQLite transaction (BEGIN IMMEDIATE ... COMMIT),
        using individual execute() calls — NOT executescript (whose implicit
        transaction control can commit a pending transaction). On ANY failure
        ROLLBACK restores the exact pre-migration state: no partial reminders
        table/indexes, schema_version stays 1. The source schema was already
        proven valid (and free of M3-only structures) by _validate_v1_schema.
        """
        path = str(self._config.path)
        conn = sqlite3.connect(path, isolation_level=None)  # manual transaction control
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                # create reminders table with the same shape AND DB-level
                # closed-set CHECK constraints as the fresh ORM-created v2
                # table (M3.1-E parity)
                cur.execute(
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
                        updated_at DATETIME NOT NULL,
                        CHECK (type IN ('day_before','hours_before','deadline')),
                        CHECK (status IN ('scheduled','fired','cancelled'))
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX ix_reminder_task_id ON reminders (task_id)"
                )
                cur.execute(
                    "CREATE INDEX ix_reminder_status_trigger ON reminders (status, trigger_at)"
                )
                cur.execute("UPDATE schema_meta SET schema_version = ?", (_V2_SUPPORTED,))
                conn.commit()  # DDL + version bump commit TOGETHER or not at all
            except Exception:
                conn.rollback()  # atomic: NOTHING from this migration persists
                raise
        finally:
            conn.close()

    def _migrate_v2_to_v3(self) -> None:
        """Owned migration v2 -> v3 (M5): add settings table, sources.deleted_at,
        M5 query indexes, bump version. Atomic (BEGIN IMMEDIATE ... COMMIT)."""
        path = str(self._config.path)
        conn = sqlite3.connect(path, isolation_level=None)
        try:
            cur = conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            try:
                cur.execute(
                    """
                    CREATE TABLE settings (
                        key VARCHAR(64) NOT NULL PRIMARY KEY,
                        value JSON NOT NULL,
                        updated_at DATETIME NOT NULL
                    )
                    """
                )
                cur.execute("ALTER TABLE sources ADD COLUMN deleted_at DATETIME")
                cur.execute("CREATE INDEX ix_task_status_source ON tasks (status, source_id)")
                cur.execute("CREATE INDEX ix_task_deadline ON tasks (deadline)")
                cur.execute("CREATE INDEX ix_extraction_source_created ON extractions (source_id, created_at)")
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
        version, tables = self._precheck()
        if version == _V1_SUPPORTED:
            # owned v1 -> v2 migration (M3): validate source schema FIRST
            # (zero mutation until proven valid), then migrate
            conn = sqlite3.connect(str(self._config.path))
            try:
                self._validate_v1_schema(conn, tables)
            finally:
                conn.close()
            self._migrate_v1_to_v2()
            # v1 -> v2 is an internal stepping stone; continue to current v3.
            self._migrate_v2_to_v3()
        elif version == _V2_SUPPORTED:
            # owned v2 -> v3 migration (M5): validate source schema FIRST
            conn = sqlite3.connect(str(self._config.path))
            try:
                self._validate_v2_schema(conn, tables)
            finally:
                conn.close()
            self._migrate_v2_to_v3()
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
