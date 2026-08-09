"""Versioned, transactional backup of CampusCue-owned data.

Task transfer intentionally leaves installation settings behind. This module is
the disaster-recovery counterpart: it preserves every CampusCue table, validates
the complete document before opening a transaction, replaces all five tables in
one commit, and leaves reminder jobs to be rebuilt from restored task deadlines.

It does not include AstrBot credentials, ``.env``, platform sessions, NapCat
state, or any other table owned by the host application.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlmodel import col, select

from campuscue import store
from campuscue.api import transfer
from campuscue.api.schemas import (
    BACKUP_KIND,
    BACKUP_VERSION,
    BackupExtraction,
    BackupOut,
    BackupProfile,
    BackupSetting,
    BackupSource,
    BackupTask,
    RestoreIn,
    RestoreOut,
)
from campuscue.models import (
    CampusExtraction,
    CampusProfile,
    CampusSetting,
    CampusSource,
    CampusTask,
    as_utc,
)


def _timestamps(row) -> dict:
    return {
        "created_at": as_utc(row.created_at),
        "updated_at": as_utc(row.updated_at),
    }


def dump_task(task: CampusTask) -> BackupTask:
    data = transfer.dump_task(task).model_dump()
    return BackupTask(
        **data,
        updated_at=as_utc(task.updated_at),
        reminded_at=as_utc(task.reminded_at),
    )


def dump_source(source: CampusSource) -> BackupSource:
    return BackupSource(
        umo=source.umo,
        display_name=source.display_name,
        course_name=source.course_name,
        source_type=source.source_type,
        enabled=source.enabled,
        authority_senders=[str(item) for item in (source.authority_senders or [])],
        stat_seen=source.stat_seen,
        stat_l1_passed=source.stat_l1_passed,
        stat_tasks_created=source.stat_tasks_created,
        **_timestamps(source),
    )


def dump_profile(profile: CampusProfile) -> BackupProfile:
    return BackupProfile(
        umo=profile.umo,
        display_name=profile.display_name,
        timezone=profile.timezone,
        lead_minutes={
            str(kind): [int(value) for value in values]
            for kind, values in (profile.lead_minutes or {}).items()
        },
        quiet_hours={str(k): str(v) for k, v in (profile.quiet_hours or {}).items()},
        confidence_threshold=profile.confidence_threshold,
        auto_confirm=profile.auto_confirm,
        **_timestamps(profile),
    )


def dump_setting(setting: CampusSetting) -> BackupSetting:
    return BackupSetting(
        key=setting.key,
        value=dict(setting.value or {}),
        **_timestamps(setting),
    )


def dump_extraction(row: CampusExtraction) -> BackupExtraction:
    return BackupExtraction(
        extraction_id=row.extraction_id,
        umo=row.umo,
        source_message_id=row.source_message_id,
        task_id=row.task_id,
        outcome=row.outcome,
        raw_text=row.raw_text,
        message_sent_at=as_utc(row.message_sent_at),
        l1_score=row.l1_score,
        l1_hits=dict(row.l1_hits or {}),
        l2_model=row.l2_model,
        l2_raw_response=row.l2_raw_response,
        l2_parsed=dict(row.l2_parsed or {}),
        l2_latency_ms=row.l2_latency_ms,
        l2_prompt_tokens=row.l2_prompt_tokens,
        l2_completion_tokens=row.l2_completion_tokens,
        l3_resolved_deadline=as_utc(row.l3_resolved_deadline),
        l3_notes=dict(row.l3_notes or {}),
        error=row.error,
        **_timestamps(row),
    )


async def export_backup() -> BackupOut:
    async with store.db_helper.get_db() as session:
        tasks = list(
            (
                await session.execute(
                    select(CampusTask).order_by(col(CampusTask.id).asc())
                )
            )
            .scalars()
            .all()
        )
        sources = list(
            (
                await session.execute(
                    select(CampusSource).order_by(col(CampusSource.id).asc())
                )
            )
            .scalars()
            .all()
        )
        profiles = list(
            (
                await session.execute(
                    select(CampusProfile).order_by(col(CampusProfile.id).asc())
                )
            )
            .scalars()
            .all()
        )
        settings = list(
            (
                await session.execute(
                    select(CampusSetting).order_by(col(CampusSetting.id).asc())
                )
            )
            .scalars()
            .all()
        )
        extractions = list(
            (
                await session.execute(
                    select(CampusExtraction).order_by(col(CampusExtraction.id).asc())
                )
            )
            .scalars()
            .all()
        )

    return BackupOut(
        kind=BACKUP_KIND,
        version=BACKUP_VERSION,
        exported_at=datetime.now(timezone.utc),
        tasks=[dump_task(row) for row in tasks],
        sources=[dump_source(row) for row in sources],
        profiles=[dump_profile(row) for row in profiles],
        settings=[dump_setting(row) for row in settings],
        extractions=[dump_extraction(row) for row in extractions],
    )


def _restore_task(row: BackupTask) -> CampusTask:
    task = transfer.to_task(row, umo=row.umo)
    task.reminder_job_ids = []
    task.reminded_at = as_utc(row.reminded_at)
    if row.updated_at:
        task.updated_at = as_utc(row.updated_at)
    return task


def _restore_source(row: BackupSource) -> CampusSource:
    data = row.model_dump(exclude={"created_at", "updated_at"})
    source = CampusSource(**data)
    if row.created_at:
        source.created_at = as_utc(row.created_at)
    if row.updated_at:
        source.updated_at = as_utc(row.updated_at)
    return source


def _restore_profile(row: BackupProfile) -> CampusProfile:
    data = row.model_dump(exclude={"created_at", "updated_at"})
    profile = CampusProfile(**data)
    if row.created_at:
        profile.created_at = as_utc(row.created_at)
    if row.updated_at:
        profile.updated_at = as_utc(row.updated_at)
    return profile


def _restore_setting(row: BackupSetting) -> CampusSetting:
    setting = CampusSetting(key=row.key, value=dict(row.value))
    if row.created_at:
        setting.created_at = as_utc(row.created_at)
    if row.updated_at:
        setting.updated_at = as_utc(row.updated_at)
    return setting


def _restore_extraction(row: BackupExtraction) -> CampusExtraction:
    data = row.model_dump(exclude={"created_at", "updated_at"})
    extraction = CampusExtraction(**data)
    if row.created_at:
        extraction.created_at = as_utc(row.created_at)
    if row.updated_at:
        extraction.updated_at = as_utc(row.updated_at)
    return extraction


async def replace_from_backup(payload: RestoreIn) -> RestoreOut:
    """Replace CampusCue tables in one transaction after Pydantic validation."""
    tasks = [_restore_task(row) for row in payload.tasks]
    sources = [_restore_source(row) for row in payload.sources]
    profiles = [_restore_profile(row) for row in payload.profiles]
    settings = [_restore_setting(row) for row in payload.settings]
    extractions = [_restore_extraction(row) for row in payload.extractions]

    async with store.db_helper.get_db() as session:
        async with session.begin():
            for model in (
                CampusExtraction,
                CampusTask,
                CampusProfile,
                CampusSource,
                CampusSetting,
            ):
                await session.execute(delete(model))
            session.add_all([*sources, *profiles, *settings, *tasks, *extractions])

    return RestoreOut(
        tasks=len(tasks),
        sources=len(sources),
        profiles=len(profiles),
        settings=len(settings),
        extractions=len(extractions),
    )


__all__ = [
    "dump_extraction",
    "dump_profile",
    "dump_setting",
    "dump_source",
    "dump_task",
    "export_backup",
    "replace_from_backup",
]
