"""M5 schema v3 migration tests (settings, sources.deleted_at, indexes)."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from campuscue.storage.database import Database, DatabaseConfig

from test_m34_storage_seal import _make_v1, _tables, _version


def test_fresh_db_is_v3_with_settings(tmp_path: Path):
    p = tmp_path / "fresh.db"
    db = Database(DatabaseConfig(path=p, env="test"))
    asyncio.run(db.initialize())
    assert _version(p) == 3
    assert "settings" in _tables(p)
    conn = sqlite3.connect(str(p))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(sources)").fetchall()}
    conn.close()
    assert "deleted_at" in cols
    asyncio.run(db.dispose())


def test_v1_migrates_to_v3_chain(tmp_path: Path):
    p = tmp_path / "chain.db"
    _make_v1(p)
    db = Database(DatabaseConfig(path=p, env="test"))
    asyncio.run(db.initialize())
    assert _version(p) == 3
    assert "settings" in _tables(p)
    asyncio.run(db.dispose())
