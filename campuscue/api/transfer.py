"""Tasks in and out as one JSON document.

Why this exists: the board's data lives in a SQLite file next to the process, so
moving to another laptop -- or handing the same task list to a second machine
before a demo -- otherwise means copying a database and hoping the schema matches.
A document that carries only the tasks survives that: it is readable, diffable,
and it does not drag the whole install along with it.

What travels, and what deliberately does not:

* Tasks travel, including their provenance (原文, 判断理由, 发信人). Provenance is
  the product's answer to "did the AI make this up" -- an exported task that lost
  it would arrive on the other machine as an unexplainable card.
* Reminder job ids do not. They name rows in the cron table of the machine that
  wrote them; carried over, they would point at alarms that do not exist and make
  a task claim it is scheduled when nothing will fire. The importer re-plans
  reminders from the deadline instead, which is the same path a new task takes.
* Delivery settings, group mappings, extraction audit rows and reminder
  preferences do not travel either. They describe *this* install -- which QQ
  account, which groups, which machine's toast -- and importing them would
  silently repoint another student's notifications.

The document is also a usable hand-written format: ``task_id``, ``umo`` and
``created_at`` may all be omitted, in which case the importer generates or
defaults them. That makes "灌入一批任务" a text file rather than a script.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import col, or_, select

from campuscue import store
from campuscue.api.schemas import (
    TRANSFER_KIND,
    TRANSFER_VERSION,
    ExportOut,
    TaskTransfer,
)
from campuscue.models import CampusTask, as_utc

TRANSFER_FIELDS = (
    "umo",
    "title",
    "task_type",
    "status",
    "deadline",
    "deadline_is_explicit",
    "location",
    "items",
    "detail",
    "confidence",
    "source_kind",
    "source_umo",
    "source_group_name",
    "source_sender_name",
    "source_message_id",
    "source_sent_at",
    "raw_text",
    "extract_reason",
    "dedup_key",
)
"""Columns an overwriting import copies onto an existing row.

Excludes ``id`` (local autoincrement), ``task_id`` (the identity being matched
on), ``reminder_job_ids`` and ``reminded_at`` (machine-local reminder state, see
the module docstring) and ``created_at`` (the row's own history -- an overwrite
corrects a task, it does not claim the task was created again).
"""


def dump_task(task: CampusTask) -> TaskTransfer:
    """One task as it goes out. Datetimes are UTC with an explicit offset."""
    return TaskTransfer(
        task_id=task.task_id,
        umo=task.umo,
        title=task.title,
        task_type=task.task_type,
        status=task.status,
        deadline=as_utc(task.deadline),
        deadline_is_explicit=task.deadline_is_explicit,
        location=task.location,
        items=[str(i) for i in (task.items or [])],
        detail=task.detail,
        confidence=task.confidence,
        source_kind=task.source_kind,
        source_umo=task.source_umo,
        source_group_name=task.source_group_name,
        source_sender_name=task.source_sender_name,
        source_message_id=task.source_message_id,
        source_sent_at=as_utc(task.source_sent_at),
        raw_text=task.raw_text,
        extract_reason=task.extract_reason,
        created_at=as_utc(task.created_at),
    )


def to_task(row: TaskTransfer, *, umo: str) -> CampusTask:
    """One incoming row as a task, ready to be added.

    ``dedup_key`` is recomputed rather than carried: it is derived from the umo,
    and an import that re-targets the group would otherwise arrive with a key
    that no longer matches its own contents -- so the next extraction of the same
    notice would not recognise it as already present.
    """
    title = row.title.strip()
    deadline = as_utc(row.deadline)
    task = CampusTask(
        umo=umo,
        title=title,
        task_type=row.task_type,
        status=row.status,
        deadline=deadline,
        deadline_is_explicit=row.deadline_is_explicit,
        location=row.location,
        items=list(row.items or []),
        detail=row.detail,
        confidence=row.confidence,
        source_kind=row.source_kind,
        source_umo=row.source_umo,
        source_group_name=row.source_group_name,
        source_sender_name=row.source_sender_name,
        source_message_id=row.source_message_id,
        source_sent_at=as_utc(row.source_sent_at),
        raw_text=row.raw_text,
        extract_reason=row.extract_reason,
        dedup_key=store.dedup_key(umo, title, deadline),
    )
    if row.task_id and (not row.umo or row.umo == umo):
        # The id only carries over when the task stays in the same group. Re-target
        # it and this is a *copy* into a different group -- keeping the id would
        # make the importer match the row it was copied from and skip the write,
        # and task_id is unique anyway, so the two could never coexist.
        task.task_id = row.task_id
    if row.created_at:
        # Preserved so the board's "newest first" ordering, and the 创建于 line on
        # the card, survive the trip. A fresh timestamp would make a semester of
        # imported tasks all look like they arrived at once.
        task.created_at = as_utc(row.created_at)
    return task


async def export_tasks(
    *, umo: str | None = None, statuses: tuple[str, ...] = ()
) -> ExportOut:
    """Build the document.

    ``umo=None`` means every group, which is the opposite of the default on the
    board's other endpoints. That is deliberate: those answer "what am I looking
    at", this one answers "give me my data", and an export that silently covered
    one group would be a backup that quietly lost the rest.
    """
    query = select(CampusTask)
    if umo:
        query = query.where(col(CampusTask.umo) == umo)
    if statuses:
        query = query.where(col(CampusTask.status).in_(statuses))
    # Oldest first: the file reads as a history, and re-importing it inserts in
    # the order the tasks were originally created.
    query = query.order_by(col(CampusTask.created_at).asc(), col(CampusTask.id).asc())

    async with store.db_helper.get_db() as session:
        result = await session.execute(query)
        tasks = list(result.scalars().all())

    rows = [dump_task(task) for task in tasks]
    return ExportOut(
        kind=TRANSFER_KIND,
        version=TRANSFER_VERSION,
        exported_at=datetime.now(timezone.utc),
        count=len(rows),
        umos=sorted({row.umo for row in rows if row.umo}),
        tasks=rows,
    )


@dataclass
class ImportReport:
    """What an import actually did, per task rather than in aggregate only.

    The ids are kept because the caller has to re-plan reminders for exactly the
    tasks it touched, and because "12 imported" with no way to find them is not a
    result a student can check.
    """

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: int = 0
    umos: set[str] = field(default_factory=set)


async def apply_import(
    rows: list[TaskTransfer],
    *,
    default_umo: str,
    force_umo: str | None = None,
    overwrite: bool = False,
) -> ImportReport:
    """Write the incoming tasks, skipping the ones already here.

    A row is "already here" if its ``task_id`` exists, or if a task in the same
    group already has its dedup key. The second test is what makes re-importing
    safe on a machine that extracted the same notice on its own: without it a
    student who exports from a laptop and imports onto a desktop that watched the
    same group ends up with every task twice, and no way to tell which is which.

    ``overwrite=True`` turns a match into an update instead, which is how a
    corrected export is used to fix an install rather than duplicate it.
    """
    report = ImportReport()
    async with store.db_helper.get_db() as session:
        async with session.begin():
            for row in rows:
                target = force_umo or row.umo or default_umo
                task = to_task(row, umo=target)

                # Autoflush makes this see rows added earlier in this same loop,
                # so a file containing the same task twice is caught too.
                result = await session.execute(
                    select(CampusTask).where(
                        or_(
                            col(CampusTask.task_id) == task.task_id,
                            (col(CampusTask.umo) == task.umo)
                            & (col(CampusTask.dedup_key) == task.dedup_key),
                        )
                    )
                )
                existing = result.scalars().first()

                if existing is not None:
                    if not overwrite:
                        report.skipped += 1
                        continue
                    for name in TRANSFER_FIELDS:
                        setattr(existing, name, getattr(task, name))
                    session.add(existing)
                    report.updated.append(existing.task_id)
                    report.umos.add(existing.umo)
                    continue

                session.add(task)
                report.created.append(task.task_id)
                report.umos.add(task.umo)
    return report


__all__ = [
    "TRANSFER_FIELDS",
    "ImportReport",
    "apply_import",
    "dump_task",
    "export_tasks",
    "to_task",
]
