"""SystemService (M5) — backup/restore/import/export and status helpers.

Backup is logical JSON (not a raw SQLite copy). Restore validates the whole
payload before replacing business rows in ONE transaction. Import supports the
V1 ``campuscue.tasks`` format and returns a per-item summary.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from campuscue.services.task_service import TaskService
from campuscue.storage.models import (
    Extraction,
    ProviderConfig,
    Reminder,
    Setting,
    Source,
    Task,
)

BACKUP_FORMAT_VERSION = 1


def _dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _model_to_dict(obj: Any, *, include_secret_ref: bool = True) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for col in obj.__table__.columns:
        name = col.name
        value = getattr(obj, name)
        if isinstance(value, datetime):
            value = _dt(value)
        if name == "secret_reference" and not include_secret_ref:
            value = None
        data[name] = value
    return data


class SystemService:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        task_service: TaskService,
        reminder_service=None,
        provider_manager=None,
    ) -> None:
        self._sf = session_factory
        self._task_service = task_service
        self._reminder_service = reminder_service
        self._provider_manager = provider_manager

    # ------------------------------------------------------------- backup

    async def create_backup(self) -> dict[str, Any]:
        async with self._sf() as session:
            sources = [ _model_to_dict(r) for r in (await session.scalars(select(Source).order_by(Source.id))).all() ]
            tasks = [ _model_to_dict(r) for r in (await session.scalars(select(Task).order_by(Task.id))).all() ]
            extractions = [ _model_to_dict(r) for r in (await session.scalars(select(Extraction).order_by(Extraction.id))).all() ]
            reminders = [ _model_to_dict(r) for r in (await session.scalars(select(Reminder).order_by(Reminder.id))).all() ]
            providers = [ _model_to_dict(r) for r in (await session.scalars(select(ProviderConfig).order_by(ProviderConfig.id))).all() ]
            settings = [ _model_to_dict(r) for r in (await session.scalars(select(Setting).order_by(Setting.key))).all() ]
        return {
            "format_version": BACKUP_FORMAT_VERSION,
            "schema_version": 3,
            "created_at": _dt(datetime.now(timezone.utc)),
            "version": "0.1.0",
            "data": {
                "sources": sources,
                "tasks": tasks,
                "extractions": extractions,
                "reminders": reminders,
                "provider_configs": providers,
                "settings": settings,
            },
        }

    # ------------------------------------------------------------- restore

    async def restore(self, payload: dict[str, Any], *, confirm_replace: bool) -> dict[str, Any]:
        if not confirm_replace:
            raise ValueError("confirm_replace must be true")
        if payload.get("format_version") != BACKUP_FORMAT_VERSION:
            raise ValueError(f"unsupported backup format_version: {payload.get('format_version')!r}")
        if payload.get("schema_version") != 3:
            raise ValueError(f"unsupported backup schema_version: {payload.get('schema_version')!r}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ValueError("backup data is missing")
        # Full validation before any mutation.
        sources = [dict(r) for r in data.get("sources", [])]
        tasks = [dict(r) for r in data.get("tasks", [])]
        extractions = [dict(r) for r in data.get("extractions", [])]
        reminders = [dict(r) for r in data.get("reminders", [])]
        providers = [dict(r) for r in data.get("provider_configs", [])]
        settings = [dict(r) for r in data.get("settings", [])]
        if not all(isinstance(x, dict) for x in sources + tasks + extractions + reminders + providers + settings):
            raise ValueError("backup data contains non-object rows")

        async with self._sf() as session:
            try:
                # Replace in FK-safe order.
                for table in (Reminder, Extraction, Task, Source, ProviderConfig, Setting):
                    await session.execute(delete(table))
                for row in sources:
                    session.add(Source(**self._coerce_datetimes(row, Source)))
                for row in tasks:
                    session.add(Task(**self._coerce_datetimes(row, Task)))
                for row in extractions:
                    session.add(Extraction(**self._coerce_datetimes(row, Extraction)))
                for row in reminders:
                    session.add(Reminder(**self._coerce_datetimes(row, Reminder)))
                for row in providers:
                    session.add(ProviderConfig(**self._coerce_datetimes(row, ProviderConfig)))
                for row in settings:
                    session.add(Setting(**self._coerce_datetimes(row, Setting)))
                await session.commit()
            except Exception:
                await session.rollback()
                raise

        # Rebuild derived runtime state after restore.
        if self._reminder_service is not None:
            await self._reminder_service.resync_all()
        # ProviderManager reads DB on demand; no cache to invalidate.
        return {"restored": True, "schema_version": 3}

    @staticmethod
    def _coerce_datetimes(row: dict[str, Any], model) -> dict[str, Any]:
        result = dict(row)
        for col in model.__table__.columns:
            name = col.name
            if name in result and isinstance(result[name], str):
                # Keep JSON values as-is; datetimes are stored as ISO strings.
                try:
                    result[name] = datetime.fromisoformat(result[name].replace("Z", "+00:00"))
                except ValueError:
                    pass  # leave original value (e.g. JSON dicts)
        return result

    # ------------------------------------------------------------- export/import

    async def export_tasks(self) -> dict[str, Any]:
        async with self._sf() as session:
            tasks = (await session.scalars(select(Task).order_by(Task.id))).all()
        return {
            "kind": "campuscue.tasks",
            "version": 1,
            "tasks": [
                {
                    "title": t.title,
                    "task_type": t.category,
                    "deadline": _dt(t.deadline),
                    "detail": t.description,
                    "course": t.course,
                    "status": t.status,
                    "priority": t.priority,
                }
                for t in tasks
            ],
        }

    async def import_tasks(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("kind") != "campuscue.tasks":
            raise ValueError("unsupported import kind (expected campuscue.tasks)")
        tasks = payload.get("tasks")
        if not isinstance(tasks, list):
            raise ValueError("tasks must be a list")
        created = skipped = duplicates = 0
        errors: list[dict[str, str]] = []
        for i, item in enumerate(tasks):
            if not isinstance(item, dict):
                errors.append({"index": str(i), "error": "not an object"})
                continue
            title = item.get("title")
            if not title:
                errors.append({"index": str(i), "error": "missing title"})
                continue
            deadline_raw = item.get("deadline")
            deadline = None
            if deadline_raw:
                try:
                    deadline = datetime.fromisoformat(str(deadline_raw).replace("Z", "+00:00"))
                except ValueError:
                    errors.append({"index": str(i), "error": f"invalid deadline {deadline_raw!r}"})
                    continue
            try:
                task = await self._task_service.create_manual_task(
                    title=str(title),
                    description=item.get("detail") or item.get("description"),
                    category=item.get("task_type") or "other",
                    course=item.get("course"),
                    deadline=deadline,
                    priority=item.get("priority") or "normal",
                    source_id=None,
                )
                created += 1
            except Exception as e:
                msg = str(e)
                if "duplicate" in msg.lower():
                    duplicates += 1
                else:
                    skipped += 1
                    errors.append({"index": str(i), "error": msg})
        return {
            "created": created,
            "skipped": skipped,
            "duplicates": duplicates,
            "errors": errors,
        }
