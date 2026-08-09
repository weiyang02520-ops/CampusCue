"""Persistence for CampusCue.

Uses astrbot's global ``db_helper`` (astrbot/core/__init__.py) rather than opening
a second engine, so campus tables live in the same SQLite file and the same WAL
transaction domain as the framework's own. ``SQLModel.metadata.create_all``
already picks the campus tables up -- being outside the ``astrbot`` package makes
no difference, because SQLModel registers every table on one shared metadata
object. Verified: no migration script is needed.

Session idiom mirrors ``SQLiteDatabase.create_cron_job``: ``async with
get_db()`` for the session, ``async with session.begin()`` for the transaction.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from astrbot.core import db_helper
from campuscue.models import (
    CampusExtraction,
    CampusProfile,
    CampusSetting,
    CampusSource,
    CampusTask,
)

DEDUP_WINDOW = timedelta(hours=36)
"""How long a task blocks a near-identical re-extraction. Longer than a day
because teachers routinely repost the same notice the next morning; short enough
that a genuinely recurring weekly task still gets created."""

# Triple-quoted so the formatter cannot split it into adjacent literals: a
# second fragment would lose the r-prefix and turn \[ into an invalid escape.
_PUNCT = re.compile(
    r"""[\s，。、！？；：“”‘’（）()\[\]【】~!@#$%^&*+=|\\/<>,.?;:'"-]+"""
)


def normalize_for_dedup(title: str) -> str:
    """Collapse a title to a comparison key.

    Punctuation and whitespace carry no meaning here: "提交实验三报告" and
    "提交 实验三 报告！" are the same task announced twice. Full fuzzy matching
    would be better but needs a similarity threshold nobody can tune without real
    data, so this stays exact-after-normalisation and errs toward creating a
    duplicate rather than swallowing a real second task.
    """
    return _PUNCT.sub("", title or "").lower()


def dedup_key(umo: str, title: str, deadline: datetime | None) -> str:
    """Identity of a task for duplicate suppression.

    Includes the deadline to the minute: a teacher moving a deadline -- even by
    an hour on the same day -- is announcing a genuinely different obligation,
    and it should surface rather than be swallowed as a duplicate of the
    original. The value is read as UTC (or treated as UTC when naive, which is
    how SQLite hands datetimes back) so the key does not shift with the server
    locale.
    """
    if deadline is None:
        stamp = "nodate"
    else:
        d = deadline
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        stamp = d.astimezone(timezone.utc).strftime("%Y%m%d%H%M")
    raw = f"{umo}|{normalize_for_dedup(title)}|{stamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def find_duplicate(
    session: AsyncSession, *, umo: str, key: str, now: datetime | None = None
) -> CampusTask | None:
    """Return a recent task with the same identity, if any.

    Dismissed tasks count as duplicates on purpose: if the student already said
    "this is not a task", re-extracting the same notice must not put it back.
    """
    since = (now or datetime.now(timezone.utc)) - DEDUP_WINDOW
    result = await session.execute(
        select(CampusTask)
        .where(col(CampusTask.umo) == umo)
        .where(col(CampusTask.dedup_key) == key)
        .where(col(CampusTask.created_at) >= since)
        .order_by(col(CampusTask.created_at).desc())
    )
    return result.scalars().first()


async def get_or_create_source(session: AsyncSession, umo: str) -> CampusSource:
    """Fetch the watched-group record, creating it on first sight."""
    result = await session.execute(
        select(CampusSource).where(col(CampusSource.umo) == umo)
    )
    source = result.scalars().first()
    if source is None:
        source = CampusSource(umo=umo)
        session.add(source)
    return source


async def get_or_create_profile(session: AsyncSession, umo: str) -> CampusProfile:
    """Fetch the student's preferences, creating defaults on first sight."""
    result = await session.execute(
        select(CampusProfile).where(col(CampusProfile.umo) == umo)
    )
    profile = result.scalars().first()
    if profile is None:
        profile = CampusProfile(umo=umo)
        session.add(profile)
    return profile


async def bump_source_stats(
    umo: str, *, seen: int = 0, l1_passed: int = 0, tasks_created: int = 0
) -> None:
    """Increment the per-group counters.

    These back the "L1 rejects most traffic for zero tokens" claim with a real
    measured ratio instead of an assertion, which matters because the extraction
    audit deliberately stores no row for an L1 rejection.
    """
    async with db_helper.get_db() as session:
        async with session.begin():
            source = await get_or_create_source(session, umo)
            source.stat_seen += seen
            source.stat_l1_passed += l1_passed
            source.stat_tasks_created += tasks_created
            session.add(source)


async def record_extraction(extraction: CampusExtraction) -> CampusExtraction:
    """Store one audit row and return it with its id populated."""
    async with db_helper.get_db() as session:
        async with session.begin():
            session.add(extraction)
        await session.refresh(extraction)
    return extraction


async def create_task(task: CampusTask) -> CampusTask:
    """Store one task and return it with its id populated."""
    async with db_helper.get_db() as session:
        async with session.begin():
            session.add(task)
        await session.refresh(task)
    return task


async def list_tasks(
    umo: str,
    *,
    statuses: tuple[str, ...] = ("active", "pending_confirm"),
    limit: int = 200,
) -> list[CampusTask]:
    """Tasks for one student, soonest deadline first.

    Undated tasks sort last: a task with no deadline cannot be urgent, and
    putting NULLs first would bury the things that actually are.
    """
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusTask)
            .where(col(CampusTask.umo) == umo)
            .where(col(CampusTask.status).in_(statuses))
            .order_by(
                col(CampusTask.deadline).is_(None),
                col(CampusTask.deadline).asc(),
                col(CampusTask.created_at).desc(),
            )
            .limit(limit)
        )
        return list(result.scalars().all())


async def get_task(task_id: str) -> CampusTask | None:
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusTask).where(col(CampusTask.task_id) == task_id)
        )
        return result.scalars().first()


async def get_task_trace(task_id: str) -> list[CampusExtraction]:
    """The extraction attempts behind one task -- the "why did the AI decide
    this" panel."""
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusExtraction)
            .where(col(CampusExtraction.task_id) == task_id)
            .order_by(col(CampusExtraction.created_at).asc())
        )
        return list(result.scalars().all())


async def update_task(task_id: str, **fields) -> CampusTask | None:
    """Patch a task by id. Unknown field names are a programming error."""
    async with db_helper.get_db() as session:
        async with session.begin():
            result = await session.execute(
                select(CampusTask).where(col(CampusTask.task_id) == task_id)
            )
            task = result.scalars().first()
            if task is None:
                return None
            for key, value in fields.items():
                if not hasattr(task, key):
                    raise AttributeError(f"CampusTask has no field {key!r}")
                setattr(task, key, value)
            session.add(task)
        await session.refresh(task)
    return task


async def count_open_tasks_between(
    umo: str, start: datetime, end: datetime
) -> list[CampusTask]:
    """Open tasks due inside a window.

    Used by analyze_opportunity to answer "do I actually have time for this"
    with the student's real schedule instead of a model's guess.
    """
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusTask)
            .where(col(CampusTask.umo) == umo)
            .where(col(CampusTask.status).in_(("active", "pending_confirm")))
            .where(col(CampusTask.deadline).is_not(None))
            .where(col(CampusTask.deadline) >= start)
            .where(col(CampusTask.deadline) <= end)
            .order_by(col(CampusTask.deadline).asc())
        )
        return list(result.scalars().all())


async def list_sources() -> list[CampusSource]:
    """Every group CampusCue has seen a message from, busiest first.

    Rows are created on first sight by ``get_or_create_source``, so this is a
    record of observed traffic rather than a configured list -- a group appears
    here because something was actually read from it, which is what makes it
    meaningful as a source filter on the board.

    Ordered by messages seen so a real course group outranks one the demo touched
    once. ``stat_seen == 0`` rows are kept: a freshly connected group that has
    not spoken yet should still be selectable.
    """
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusSource).order_by(
                col(CampusSource.stat_seen).desc(),
                col(CampusSource.umo).asc(),
            )
        )
        return list(result.scalars().all())


async def get_profile(umo: str) -> CampusProfile:
    """The student's reminder preferences, created with defaults on first read.

    Committed on creation rather than returned detached: the settings panel reads
    this before it can write, and a defaults object that vanishes would make the
    first save look like it changed everything.
    """
    async with db_helper.get_db() as session:
        async with session.begin():
            profile = await get_or_create_profile(session, umo)
        await session.refresh(profile)
    return profile


async def update_profile(umo: str, **fields) -> CampusProfile:
    """Patch preferences by umo. Unknown field names are a programming error."""
    async with db_helper.get_db() as session:
        async with session.begin():
            profile = await get_or_create_profile(session, umo)
            for key, value in fields.items():
                if not hasattr(profile, key):
                    raise AttributeError(f"CampusProfile has no field {key!r}")
                setattr(profile, key, value)
            session.add(profile)
        await session.refresh(profile)
    return profile


async def get_source(umo: str) -> CampusSource | None:
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusSource).where(col(CampusSource.umo) == umo)
        )
        return result.scalars().first()


async def update_source(umo: str, **fields) -> CampusSource:
    """Patch a watched group, creating its row if this is the first time it is
    named.

    Creating on write matters for the default group: on a fresh install the board
    offers a umo that has no row yet (``list_sources`` synthesises it), and
    telling CampusCue "this group is 软件工程" must not 404 just because nobody
    has spoken in it.
    """
    async with db_helper.get_db() as session:
        async with session.begin():
            source = await get_or_create_source(session, umo)
            for key, value in fields.items():
                if not hasattr(source, key):
                    raise AttributeError(f"CampusSource has no field {key!r}")
                setattr(source, key, value)
            session.add(source)
        await session.refresh(source)
    return source


async def count_tasks_by_umo() -> dict[str, int]:
    """Open task count per group, for the source picker's badges.

    Separate query rather than a join on ``list_sources``: a group with tasks but
    no source row (possible for a hand-created task on an unseen umo) still has
    to be counted, and the picker merges the two.
    """
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(col(CampusTask.umo), func.count())
            .where(col(CampusTask.status).in_(("active", "pending_confirm")))
            .group_by(col(CampusTask.umo))
        )
        return {str(umo): int(count) for umo, count in result.all()}


# --- process-wide settings ------------------------------------------------


async def get_setting(key: str, default=None):
    """Read one global setting, or ``default`` when it was never written."""
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(CampusSetting).where(col(CampusSetting.key) == key)
        )
        row = result.scalars().first()
    if row is None:
        return default
    stored = row.value or {}
    return stored.get("v", default)


async def set_setting(key: str, value) -> None:
    """Write one global setting, creating the row on first write."""
    async with db_helper.get_db() as session:
        async with session.begin():
            result = await session.execute(
                select(CampusSetting).where(col(CampusSetting.key) == key)
            )
            row = result.scalars().first()
            if row is None:
                row = CampusSetting(key=key, value={"v": value})
            else:
                row.value = {"v": value}
            session.add(row)


# --- deletion -------------------------------------------------------------
# The only destructive paths in the module. Both exist for one reason: a demo
# database accumulates fixture groups, and shipping those to a live judging
# session makes every real number on the board unreadable.


async def delete_tasks_by_umo(umo: str) -> list[str]:
    """Delete every task belonging to one group.

    Returns the cron job ids the deleted tasks owned, so the caller can cancel
    them. Deliberately not cancelling them here: ``store`` must stay importable
    without the scheduler (the replay script and the tests rely on that).
    """
    job_ids: list[str] = []
    async with db_helper.get_db() as session:
        async with session.begin():
            result = await session.execute(
                select(CampusTask).where(col(CampusTask.umo) == umo)
            )
            for task in result.scalars().all():
                job_ids.extend(str(j) for j in (task.reminder_job_ids or []))
                await session.delete(task)
    return job_ids


async def delete_source(umo: str, *, with_tasks: bool = True) -> dict:
    """Remove a watched group, and by default everything extracted from it.

    Returns a summary ({"tasks": n, "extractions": n, "job_ids": [...]}) so the
    caller can report what was actually removed instead of claiming success.
    """
    job_ids: list[str] = []
    task_count = 0
    if with_tasks:
        # Counted before the delete, not from the job ids: a task with no reminder
        # owns no job id, so counting job ids would under-report the deletion.
        task_count = await count_tasks_for_umo(umo)
        job_ids = await delete_tasks_by_umo(umo)

    removed = {"tasks": task_count, "extractions": 0}
    async with db_helper.get_db() as session:
        async with session.begin():
            if with_tasks:
                result = await session.execute(
                    select(CampusExtraction).where(col(CampusExtraction.umo) == umo)
                )
                rows = list(result.scalars().all())
                removed["extractions"] = len(rows)
                for row in rows:
                    await session.delete(row)

            result = await session.execute(
                select(CampusSource).where(col(CampusSource.umo) == umo)
            )
            source = result.scalars().first()
            if source is not None:
                await session.delete(source)

            result = await session.execute(
                select(CampusProfile).where(col(CampusProfile.umo) == umo)
            )
            profile = result.scalars().first()
            if profile is not None:
                await session.delete(profile)

    removed["job_ids"] = job_ids
    return removed


async def count_tasks_for_umo(umo: str) -> int:
    """How many tasks a group owns, in any status -- shown in the delete prompt."""
    async with db_helper.get_db() as session:
        result = await session.execute(
            select(func.count())
            .select_from(CampusTask)
            .where(col(CampusTask.umo) == umo)
        )
        return int(result.scalar() or 0)


__all__ = [
    "DEDUP_WINDOW",
    "bump_source_stats",
    "count_tasks_for_umo",
    "delete_source",
    "delete_tasks_by_umo",
    "get_setting",
    "set_setting",
    "db_helper",
    "count_open_tasks_between",
    "count_tasks_by_umo",
    "create_task",
    "dedup_key",
    "find_duplicate",
    "get_or_create_profile",
    "get_or_create_source",
    "get_profile",
    "get_source",
    "get_task",
    "get_task_trace",
    "list_sources",
    "list_tasks",
    "normalize_for_dedup",
    "record_extraction",
    "update_profile",
    "update_source",
    "update_task",
]
