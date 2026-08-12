"""M3.2 Final Gate Fix regression tests (external review round).

A. quiet-hours: canonical is_inside_quiet_hours predicate; every returned
   reminder satisfies BOTH (trigger <= deadline) AND (trigger outside quiet);
   overnight-only contract fail-fast.
B. schema_meta exactly-one-row is a GLOBAL invariant validated in _precheck
   before version dispatch ([1,2] and [2,1] both REFUSE, zero mutation).
C. REAL composition-root wiring test: CampusRuntime must actually consume
   ReminderConfig (spy the production ReminderService constructor — no
   duplicated wiring logic in the test).
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)


def _local(y, mo, d, h, mi=0, s=0):
    return datetime(y, mo, d, h, mi, s, 0, tzinfo=TZ)


def _task(*, deadline):
    from campuscue.storage.models import Task

    return Task(
        id=1, title="作业", description=None, category="homework", course=None,
        deadline=deadline.astimezone(timezone.utc), status="pending",
        priority="normal", confidence=0.9, dedup_key=None, source_id=None,
        source_message_id=None, source_text_reference=None,
        created_at=NOW, updated_at=NOW,
    )


# ------------------------------------------------------------------ A: quiet-hours contract

class TestQuietHoursContract:
    def test_canonical_predicate_boundaries(self):
        """Boundary: 22:59:59 allowed; 23:00:00 quiet; 07:59:59 quiet;
        08:00:00 allowed (default 23-08)."""
        from campuscue.tasks.reminder_policy import DEFAULT_POLICY, is_inside_quiet_hours

        p = DEFAULT_POLICY
        assert is_inside_quiet_hours(_local(2026, 8, 10, 22, 59, 59), p) is False  # allowed
        assert is_inside_quiet_hours(_local(2026, 8, 10, 23, 0, 0), p) is True  # quiet
        assert is_inside_quiet_hours(_local(2026, 8, 11, 7, 59, 59), p) is True  # quiet
        assert is_inside_quiet_hours(_local(2026, 8, 11, 8, 0, 0), p) is False  # allowed

    def test_deadline_friday_2359_both_invariants(self):
        """deadline Friday 23:59: every returned reminder is <= deadline AND
        outside quiet hours (07:59:59 would violate the quiet invariant — the
        clamp must target 22:59:59, the latest allowed pre-quiet moment)."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        deadline_local = _local(2026, 8, 14, 23, 59)  # Friday 23:59 +08
        r = plan_desired_reminders(task=_task(deadline=deadline_local), now=NOW, tz=TZ)
        assert r, "expected reminders for future 23:59 deadline"
        for d in r:
            local_t = d.trigger_at_utc.astimezone(TZ)
            assert d.trigger_at_utc <= deadline_local.astimezone(timezone.utc), "post-deadline!"
            assert not (local_t.hour >= 23 or local_t.hour < 8), f"inside quiet: {local_t}"

    def test_early_morning_deadline_both_invariants(self):
        """deadline 06:00 inside quiet: no post-deadline AND no returned
        reminder inside quiet hours (deadline intent discarded)."""
        from campuscue.tasks.reminder_policy import plan_desired_reminders

        deadline_local = _local(2026, 8, 14, 6, 0)
        r = plan_desired_reminders(task=_task(deadline=deadline_local), now=NOW, tz=TZ)
        for d in r:
            local_t = d.trigger_at_utc.astimezone(TZ)
            assert d.trigger_at_utc <= deadline_local.astimezone(timezone.utc)
            assert not (local_t.hour >= 23 or local_t.hour < 8)
        # deadline intent itself is inside quiet -> cannot be scheduled
        assert all(d.type != "deadline" for d in r) or not r

    def test_configured_overnight_window_respected(self):
        """Configured supported overnight window behaves per contract
        (e.g. 22-07: 21:59:59 allowed, 22:00:00 quiet, 06:59:59 quiet,
        07:00:00 allowed)."""
        from campuscue.tasks.reminder_policy import (
            ReminderPolicy,
            is_inside_quiet_hours,
        )

        p = ReminderPolicy(quiet_start_hour=22, quiet_end_hour=7)
        assert is_inside_quiet_hours(_local(2026, 8, 10, 21, 59, 59), p) is False
        assert is_inside_quiet_hours(_local(2026, 8, 10, 22, 0, 0), p) is True
        assert is_inside_quiet_hours(_local(2026, 8, 11, 6, 59, 59), p) is True
        assert is_inside_quiet_hours(_local(2026, 8, 11, 7, 0, 0), p) is False

    def test_unsupported_window_fails_fast(self):
        """E: non-overnight / invalid quiet configurations rejected at policy
        construction (overnight-only contract, explicit)."""
        from campuscue.tasks.reminder_policy import ReminderPolicy

        with pytest.raises(ValueError, match="OVERNIGHT"):
            ReminderPolicy(quiet_start_hour=12, quiet_end_hour=14)  # same-day
        with pytest.raises(ValueError, match="OVERNIGHT"):
            ReminderPolicy(quiet_start_hour=8, quiet_end_hour=8)  # equal
        with pytest.raises(ValueError, match="hour 0-23"):
            ReminderPolicy(quiet_start_hour=24, quiet_end_hour=8)
        with pytest.raises(ValueError, match="hour 0-23"):
            ReminderPolicy(quiet_start_hour=23, quiet_end_hour=-1)

    def test_quiet_end_zero_is_valid(self):
        """Boundary: quiet_end_hour=0 is a valid overnight window (start > end);
        window 23-0 = only hour 23 is quiet (hour < 0 never matches)."""
        from campuscue.tasks.reminder_policy import (
            ReminderPolicy,
            is_inside_quiet_hours,
        )

        p = ReminderPolicy(quiet_start_hour=23, quiet_end_hour=0)
        assert is_inside_quiet_hours(_local(2026, 8, 10, 23, 30), p) is True
        assert is_inside_quiet_hours(_local(2026, 8, 11, 0, 30), p) is False
        assert is_inside_quiet_hours(_local(2026, 8, 11, 8, 0), p) is False


# ------------------------------------------------------------------ B: schema_meta global exactly-one

class TestSchemaMetaGlobalSingle:
    def _build_db(self, path, versions):
        conn = sqlite3.connect(str(path))
        conn.executescript(
            "CREATE TABLE schema_meta (id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, "
            "schema_version INTEGER NOT NULL UNIQUE);"
        )
        for v in versions:
            conn.execute("INSERT INTO schema_meta (schema_version) VALUES (?)", (v,))
        conn.commit()
        conn.close()

    def test_conflicting_versions_12_refused(self, tmp_path):
        """[1,2] order -> REFUSE, ZERO MUTATION."""
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        p = tmp_path / "m12.db"
        self._build_db(p, [1, 2])
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="exactly one"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before

    def test_conflicting_versions_21_refused(self, tmp_path):
        """[2,1] order -> REFUSE, ZERO MUTATION (must NOT resolve as v2)."""
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        p = tmp_path / "m21.db"
        self._build_db(p, [2, 1])
        before = open(str(p), "rb").read()
        db = Database(DatabaseConfig(path=p, env="test"))
        with pytest.raises(SchemaRefusedError, match="exactly one"):
            asyncio.run(db.initialize())
        assert open(str(p), "rb").read() == before


# ------------------------------------------------------------------ C: composition-root wiring

class TestCompositionRootWiring:
    @pytest.mark.asyncio
    async def test_runtime_consumes_reminder_config(self, monkeypatch, tmp_path):
        """C: CampusRuntime's real composition path must feed ReminderConfig
        into the production ReminderService/ReminderPolicy. The test SPIES the
        production constructor — it does not rewrite the wiring logic."""
        from dataclasses import replace

        from campuscue.app import runtime as runtime_mod
        from campuscue.config import (
            ReminderConfig,
            RuntimeConfig,
            TaskPipelineConfig,
        )
        from campuscue.services.reminder_service import ReminderService
        from campuscue.tasks.reminder_policy import ReminderPolicy

        db_path = tmp_path / "wiring.db"
        cfg = replace(
            RuntimeConfig(),
            tasks=TaskPipelineConfig(
                enabled=True,
                database_path=str(db_path),
                database_path_explicit=True,
                timezone="Asia/Shanghai",
            ),
            reminders=ReminderConfig(
                enabled=True,
                timezone="America/New_York",
                min_lead_seconds=120.0,
                quiet_start_hour=22,
                quiet_end_hour=9,
            ),
        )

        captured = {}

        orig_init = ReminderService.__init__

        def spy_init(self, reminders, tasks, *, scheduler=None, clock=None,
                     timezone=None, policy=None, **kw):
            captured["timezone"] = timezone
            captured["policy"] = policy
            orig_init(self, reminders, tasks, scheduler=scheduler, clock=clock,
                      timezone=timezone, policy=policy, **kw)

        ReminderService.__init__ = spy_init
        try:
            rt = runtime_mod.CampusRuntime(cfg)
            # exercise the REAL composition path (task pipeline init); router
            # is required by _init_task_pipeline — build it exactly as start()
            # would (real production wiring, not test logic)
            from campuscue.core.router import Router

            rt.router = Router()
            await rt._init_task_pipeline()
        finally:
            ReminderService.__init__ = orig_init
            await rt._dispose_database()

        assert captured["timezone"] is not None
        assert captured["timezone"].key == "America/New_York"
        policy = captured["policy"]
        assert isinstance(policy, ReminderPolicy)
        assert policy.min_lead_seconds == 120.0
        assert policy.quiet_start_hour == 22
        assert policy.quiet_end_hour == 9
