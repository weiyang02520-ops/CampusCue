"""Storage-layer invariants, including the timezone trap.

The ``as_utc`` test exists because of a bug found by running the pipeline, not by
reading it: SQLite has no timezone type, so a timezone-aware UTC datetime comes
back naive. Calling ``astimezone`` on that value makes Python treat it as local
time, which shifted every deadline by 8 hours and rendered "周五23:59" as
"周五15:59" on the task card. A deadline that is wrong by most of a day, but still
looks plausible, is the worst possible failure for this product.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.models import as_utc
from campuscue.store import DEDUP_WINDOW, dedup_key, normalize_for_dedup

CN = ZoneInfo("Asia/Shanghai")


# =========================================================================
# as_utc -- the 8-hour bug
# =========================================================================


def test_naive_value_from_sqlite_is_read_back_as_utc():
    """A naive datetime out of the database is UTC, not local time."""
    naive = datetime(2026, 7, 31, 15, 59)  # what SQLite hands back

    restored = as_utc(naive)

    assert restored.tzinfo is not None
    assert restored.utcoffset() == timedelta(0)
    assert restored.astimezone(CN).hour == 23, (
        "23:59 Beijing was stored as 15:59 UTC; reading it back as local time "
        "would display it as 15:59 and move the deadline most of a day"
    )
    assert restored.astimezone(CN).minute == 59


def test_aware_value_passes_through_unchanged():
    aware = datetime(2026, 7, 31, 23, 59, tzinfo=CN)

    restored = as_utc(aware)

    assert restored == aware
    assert restored.utcoffset() == timedelta(0)


def test_none_is_preserved():
    """An undated task must stay undated rather than becoming the epoch."""
    assert as_utc(None) is None


def test_round_trip_through_a_naive_column_preserves_the_instant():
    """Simulate the full write-then-read cycle."""
    original = datetime(2026, 7, 31, 23, 59, tzinfo=CN)

    stored = original.astimezone(timezone.utc)
    as_sqlite_returns_it = stored.replace(tzinfo=None)  # what actually happens
    recovered = as_utc(as_sqlite_returns_it)

    assert recovered == original
    assert recovered.astimezone(CN).strftime("%m-%d %H:%M") == "07-31 23:59"


# =========================================================================
# dedup
# =========================================================================


def test_normalization_ignores_punctuation_and_spacing():
    assert normalize_for_dedup("提交实验三报告") == normalize_for_dedup(
        "提交 实验三 报告！"
    )
    assert normalize_for_dedup("提交实验三报告") == normalize_for_dedup(
        "【提交实验三报告】"
    )


def test_same_notice_reposted_is_one_task():
    deadline = datetime(2026, 7, 31, 15, 59, tzinfo=timezone.utc)

    first = dedup_key("umo-1", "提交实验三报告", deadline)
    second = dedup_key("umo-1", "提交 实验三报告", deadline)

    assert first == second


def test_moving_the_deadline_creates_a_distinct_task():
    """A teacher extending a deadline is announcing a different obligation, and
    it must surface rather than be suppressed as a duplicate."""
    original = datetime(2026, 7, 31, 15, 59, tzinfo=timezone.utc)
    extended = datetime(2026, 8, 3, 15, 59, tzinfo=timezone.utc)

    assert dedup_key("umo-1", "提交实验三报告", original) != dedup_key(
        "umo-1", "提交实验三报告", extended
    )


def test_same_title_in_different_groups_is_not_a_duplicate():
    """Two courses can both assign 实验三; they are separate obligations."""
    deadline = datetime(2026, 7, 31, 15, 59, tzinfo=timezone.utc)

    assert dedup_key("group-a", "提交实验三报告", deadline) != dedup_key(
        "group-b", "提交实验三报告", deadline
    )


def test_undated_tasks_dedup_by_title_alone():
    assert dedup_key("umo-1", "交材料", None) == dedup_key("umo-1", "交材料", None)


def test_dedup_window_survives_an_overnight_repost():
    """Teachers routinely repost a notice the next morning."""
    assert DEDUP_WINDOW >= timedelta(hours=24)


# =========================================================================
# schema
# =========================================================================


def test_campus_tables_register_on_the_shared_metadata():
    """The campus tables live outside the astrbot package but must still be
    created by ``SQLModel.metadata.create_all`` -- this is what makes a migration
    script unnecessary."""
    from sqlmodel import SQLModel

    import campuscue.models  # noqa: F401  (import registers the tables)

    names = set(SQLModel.metadata.tables)

    assert {
        "campus_tasks",
        "campus_extractions",
        "campus_sources",
        "campus_profiles",
    } <= names


@pytest.mark.parametrize(
    "field",
    ["source_message_id", "raw_text", "extract_reason", "source_sent_at", "confidence"],
)
def test_task_keeps_its_provenance(field: str):
    """Every field the trace panel needs must exist on the task itself, so a
    task can always answer "where did you come from"."""
    from campuscue.models import CampusTask

    assert field in CampusTask.model_fields
