"""Owned SQLite database module (M2a).

Responsibilities:
- AsyncEngine + async session factory (SQLAlchemy 2.x + aiosqlite)
- initialize schema (create_all + schema_meta version check)
- dispose

SQLite pragmas: foreign_keys=ON, busy_timeout, WAL for file-backed DB.
Test isolation (M2, hard gate): CAMPUSCUE_ENV=test REQUIRES an explicit
test database path; never silently fall back to the normal DB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from campuscue.storage.models import Base, SCHEMA_VERSION, SchemaMeta

_WAL_PRAGMAS = ("wal", "journal")


@dataclass(frozen=True)
class DatabaseConfig:
    path: str | Path  # e.g. "data/campuscue.db"; ":memory:" not supported for async
    env: str = os.environ.get("CAMPUSCUE_ENV", "production")
    busy_timeout_ms: int = 30000


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

    async def initialize(self) -> None:
        """Create engine, apply pragmas, create schema, verify version."""
        url = self._url()
        kwargs: dict = {"connect_args": {}}
        if "?" in url:
            raise RuntimeError("url query strings not supported; configure pragmas in code")
        self._engine = create_async_engine(url, connect_args={"timeout": self._config.busy_timeout_ms / 1000})

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_pragmas(dbapi_conn, _record):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute(f"PRAGMA busy_timeout={self._config.busy_timeout_ms}")
            # WAL only for file-backed application DBs (tests use temp files; also file-backed)
            if self._config.env != "test":
                cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await self._check_version()

    async def _check_version(self) -> None:
        # ensure our schema version row exists
        async with self.session() as session:
            row = await session.scalar(select(SchemaMeta).where(SchemaMeta.schema_version == SCHEMA_VERSION))
            if row is None:
                session.add(SchemaMeta(schema_version=SCHEMA_VERSION))
                await session.commit()
        # ALWAYS detect any OTHER (newer/unknown) version rows -> fail clearly
        async with self.session() as session:
            versions = list((await session.scalars(select(SchemaMeta.schema_version))).all())
        others = [v for v in versions if v != SCHEMA_VERSION]
        if others:
            raise RuntimeError(
                f"unsupported schema version(s) {others!r}; this build supports version {SCHEMA_VERSION}. "
                "Refusing to open a newer/unknown database."
            )

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
