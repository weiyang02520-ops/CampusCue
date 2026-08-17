"""Single-table persistence/query primitives. No business orchestration.

Each repository method opens its own explicit short transaction via the
session factory. No hidden global session.

M2a.1 hardening:
- closed-set enums enforced at the repository boundary (invalid strings rejected)
- secret_reference validated before persistence (shared rule with Provider)
- Clock injection: created_at/updated_at set explicitly from clock.utcnow()
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from campuscue.providers.validation import (
    validate_provider_config_numeric,
    validate_secret_reference,
)
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import (
    ExtractionStatus,
    ReminderStatus,
    ReminderType,
    TaskCategory,
    TaskPriority,
    TaskStatus,
)
from campuscue.storage.models import (
    Extraction,
    ProviderConfig,
    Reminder,
    Source,
    Task,
)

T = TypeVar("T", bound=DeclarativeBase)


class RepositoryError(Exception):
    pass


class DuplicateError(RepositoryError):
    """Unique constraint violation (e.g. duplicate source identity or task)."""


class NotFoundError(RepositoryError):
    pass


class _BaseRepo(Generic[T]):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], clock: Clock | None = None) -> None:
        self._sf = session_factory
        self._clock = clock or SystemClock()

    def _now(self) -> datetime:
        now = self._clock.utcnow()
        if now.tzinfo is None:
            raise ValueError("clock.utcnow() must return timezone-aware UTC datetime")
        return now.astimezone(timezone.utc)


def _require_enum(enum_cls, value: str, field: str) -> str:
    """Closed-set enforcement: accept enum instance or canonical value; reject others."""
    if isinstance(value, enum_cls):
        return value.value
    try:
        return enum_cls(value).value
    except ValueError:
        raise ValueError(f"invalid {field}: {value!r} (allowed: {[e.value for e in enum_cls]})") from None


class _Unset:
    def __repr__(self) -> str:  # pragma: no cover - debug only
        return "<UNSET>"


# Sentinel distinguishing "field not provided" (leave unchanged) from an
# explicit None (clear the value) — used by M4 update primitives.
_UNSET = _Unset()


class SourceRepository(_BaseRepo[Source]):
    async def create(
        self,
        *,
        platform: str,
        conversation_id: str,
        name: str = "",
        enabled: bool = True,
        auto_extract: bool = True,
        context_window: int = 5,
        privacy_policy: str = "default",
    ) -> Source:
        if context_window < 1:
            raise ValueError("context_window must be >= 1")
        now = self._now()
        async with self._sf() as session:
            source = Source(
                platform=platform,
                conversation_id=conversation_id,
                name=name,
                enabled=enabled,
                auto_extract=auto_extract,
                context_window=context_window,
                privacy_policy=privacy_policy,
                created_at=now,
                updated_at=now,
            )
            session.add(source)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise DuplicateError(
                    f"source already exists: ({platform}, {conversation_id})"
                ) from None
            await session.refresh(source)
            return source

    async def get_by_identity(self, platform: str, conversation_id: str) -> Source | None:
        async with self._sf() as session:
            return await session.scalar(
                select(Source).where(
                    Source.platform == platform, Source.conversation_id == conversation_id
                )
            )

    async def get(self, source_id: int) -> Source:
        async with self._sf() as session:
            source = await session.get(Source, source_id)
            if source is None:
                raise NotFoundError(f"source {source_id} not found")
            return source

    async def list_all(self) -> list[Source]:
        async with self._sf() as session:
            return list((await session.scalars(select(Source).order_by(Source.id))).all())

    async def update(
        self,
        source_id: int,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        auto_extract: bool | None = None,
        context_window: int | None = None,
    ) -> Source:
        now = self._now()
        async with self._sf() as session:
            source = await session.get(Source, source_id)
            if source is None:
                raise NotFoundError(f"source {source_id} not found")
            if name is not None:
                source.name = name
            if enabled is not None:
                source.enabled = enabled
            if auto_extract is not None:
                source.auto_extract = auto_extract
            if context_window is not None:
                if context_window < 1:
                    raise ValueError("context_window must be >= 1")
                source.context_window = context_window
            source.updated_at = now
            await session.commit()
            await session.refresh(source)
            return source


class TaskRepository(_BaseRepo[Task]):
    async def create(
        self,
        *,
        title: str,
        description: str | None = None,
        category: str = "other",
        course: str | None = None,
        deadline: datetime | None = None,
        status: str = "pending",
        priority: str = "normal",
        confidence: float | None = None,
        dedup_key: str | None = None,
        source_id: int | None = None,
        source_message_id: str | None = None,
        source_text_reference: str | None = None,
    ) -> Task:
        category_v = _require_enum(TaskCategory, category, "category")
        status_v = _require_enum(TaskStatus, status, "status")
        priority_v = _require_enum(TaskPriority, priority, "priority")
        if deadline is not None and deadline.tzinfo is None:
            raise ValueError("naive deadline rejected at storage boundary")
        now = self._now()
        async with self._sf() as session:
            task = Task(
                title=title,
                description=description,
                category=category_v,
                course=course,
                deadline=deadline.astimezone(timezone.utc) if deadline else None,
                status=status_v,
                priority=priority_v,
                confidence=confidence,
                dedup_key=dedup_key,
                source_id=source_id,
                source_message_id=source_message_id,
                source_text_reference=source_text_reference,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise DuplicateError(
                    f"task duplicate for source_message_id={source_message_id!r}"
                ) from None
            await session.refresh(task)
            return task

    async def get(self, task_id: int) -> Task:
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            return task

    async def find_by_source_message(self, source_id: int, source_message_id: str) -> Task | None:
        async with self._sf() as session:
            return await session.scalar(
                select(Task).where(
                    Task.source_id == source_id, Task.source_message_id == source_message_id
                )
            )

    async def find_recent_by_dedup_key(self, dedup_key: str, limit: int = 10) -> list[Task]:
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task)
                        .where(Task.dedup_key == dedup_key)
                        .order_by(Task.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )

    async def find_recent_for_source(self, source_id: int, cutoff: datetime, limit: int = 100) -> list[Task]:
        """Recent tasks for one source created after cutoff (M2b.1 dedup window query)."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task)
                        .where(Task.source_id == source_id, Task.created_at >= cutoff)
                        .order_by(Task.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Task]:
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
                    )
                ).all()
            )

    async def list_for_source(self, source_id: int, limit: int = 200) -> list[Task]:
        """M4: source-scoped list. Agent tools use THIS query — the global
        list_all is never exposed to tools (M4 §15 no global task leak)."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task)
                        .where(Task.source_id == source_id)
                        .order_by(Task.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )

    async def update_deadline(self, task_id: int, deadline: datetime | None) -> Task:
        """M3: deadline mutation primitive (persistence only; reminder
        orchestration lives in TaskService)."""
        if deadline is not None and deadline.tzinfo is None:
            raise ValueError("naive deadline rejected at storage boundary")
        now = self._now()
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            task.deadline = deadline.astimezone(timezone.utc) if deadline else None
            task.updated_at = now
            await session.commit()
            await session.refresh(task)
            return task

    async def set_status(self, task_id: int, status: str) -> Task:
        """M3: status mutation primitive (closed-set enforced; reminder
        orchestration lives in TaskService)."""
        status_v = _require_enum(TaskStatus, status, "status")
        now = self._now()
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            task.status = status_v
            task.updated_at = now
            await session.commit()
            await session.refresh(task)
            return task

    async def delete(self, task_id: int) -> None:
        """M3: delete primitive. Caller (TaskService) cancels reminders FIRST
        (FK-safe ordering); this removes the task row only."""
        now = self._now()
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            # FK-safe: reminders for this task must be cancelled/removed by the
            # service layer before this call; the reminders table has
            # FK to tasks.id so delete fails if rows remain.
            await session.delete(task)
            task_updated = task  # noqa: F841 (updated_at bookkeeping not needed on delete)
            await session.commit()

    async def update_fields(
        self,
        task_id: int,
        *,
        title: str | None = None,
        course: str | None = None,
        deadline: datetime | object = _UNSET,
    ) -> Task:
        """M4: combined field update primitive (persistence only; reminder
        orchestration lives in TaskService). None = leave unchanged.
        deadline=_UNSET leaves it unchanged; deadline=None CLEARS it; naive
        deadlines rejected at the storage boundary."""
        if deadline is not _UNSET and deadline is not None and deadline.tzinfo is None:
            raise ValueError("naive deadline rejected at storage boundary")
        now = self._now()
        async with self._sf() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise NotFoundError(f"task {task_id} not found")
            if title is not None:
                title = title.strip()
                if not title:
                    raise ValueError("title must not be empty")
                task.title = title
            if course is not None:
                task.course = course.strip() or None
            if deadline is not _UNSET:
                task.deadline = deadline.astimezone(timezone.utc) if deadline else None
            task.updated_at = now
            await session.commit()
            await session.refresh(task)
            return task

    async def list_pending_with_deadline(self) -> list[Task]:
        """M3.3-A: ALL tasks that need reminder planning (status=pending AND
        deadline IS NOT NULL). Dedicated query — never silently truncated:
        every relevant task is reconciled on startup, regardless of count."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task).where(
                            Task.status == TaskStatus.PENDING.value,
                            Task.deadline.is_not(None),
                        )
                    )
                ).all()
            )


class ExtractionRepository(_BaseRepo[Extraction]):
    async def create(
        self,
        *,
        source_id: int | None,
        source_message_id: str,
        trace_id: str,
        provider: str | None = None,
        model: str | None = None,
        status: str = "success",
        confidence: float | None = None,
        raw_result: str | None = None,
        normalized_result: str | None = None,
        audit: str | None = None,
        error: str | None = None,
    ) -> Extraction:
        status_v = _require_enum(ExtractionStatus, status, "status")
        now = self._now()
        async with self._sf() as session:
            row = Extraction(
                source_id=source_id,
                source_message_id=source_message_id,
                trace_id=trace_id,
                provider=provider,
                model=model,
                status=status_v,
                confidence=confidence,
                raw_result=raw_result,
                normalized_result=normalized_result,
                audit=audit,
                error=error,
                created_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_for_message(self, source_message_id: str, limit: int = 50) -> list[Extraction]:
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Extraction)
                        .where(Extraction.source_message_id == source_message_id)
                        .order_by(Extraction.created_at.desc())
                        .limit(limit)
                    )
                ).all()
            )


class ReminderRepository(_BaseRepo[Reminder]):
    """Single-table persistence for reminder FACTS (M3). No business rules:
    no planning offsets, no task mutation, no scheduler ops, no delivery."""

    async def create(
        self,
        *,
        task_id: int,
        trigger_at: datetime,
        type: str,
        status: str = ReminderStatus.SCHEDULED.value,
        job_id: str | None = None,
        error: str | None = None,
    ) -> Reminder:
        type_v = _require_enum(ReminderType, type, "type")
        status_v = _require_enum(ReminderStatus, status, "status")
        if trigger_at.tzinfo is None:
            raise ValueError("naive trigger_at rejected at storage boundary")
        now = self._now()
        async with self._sf() as session:
            row = Reminder(
                task_id=task_id,
                trigger_at=trigger_at.astimezone(timezone.utc),
                type=type_v,
                status=status_v,
                job_id=job_id,
                error=error,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def get(self, reminder_id: int) -> Reminder:
        async with self._sf() as session:
            row = await session.get(Reminder, reminder_id)
            if row is None:
                raise NotFoundError(f"reminder {reminder_id} not found")
            return row

    async def list_for_task(self, task_id: int) -> list[Reminder]:
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Reminder).where(Reminder.task_id == task_id).order_by(Reminder.trigger_at)
                    )
                ).all()
            )

    async def list_for_source(self, source_id: int) -> list[Reminder]:
        """M4: reminders of tasks visible in ONE source (reminder_list tool).
        JOIN through tasks — the global reminder view is never exposed to
        Agent tools (M4 §23 source authorization stays in front)."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Reminder)
                        .join(Task, Task.id == Reminder.task_id)
                        .where(Task.source_id == source_id)
                        .order_by(Reminder.trigger_at)
                    )
                ).all()
            )

    async def list_scheduled(self) -> list[Reminder]:
        """All active (scheduled) reminder facts — the resync source of truth."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Reminder)
                        .where(Reminder.status == ReminderStatus.SCHEDULED.value)
                        .order_by(Reminder.trigger_at)
                    )
                ).all()
            )

    async def list_scheduled_for_task(self, task_id: int) -> list[Reminder]:
        """Active (scheduled) reminder facts of ONE task (M3.3-A reconciliation)."""
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Reminder).where(
                            Reminder.task_id == task_id,
                            Reminder.status == ReminderStatus.SCHEDULED.value,
                        )
                    )
                ).all()
            )

    async def cancel_for_task(self, task_id: int, *, now: datetime | None = None) -> int:
        """Cancel all scheduled reminders of a task (DB facts). Returns count.
        Caller supplies `now` (aware UTC) for updated_at; defaults to clock."""
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(Reminder).where(
                        Reminder.task_id == task_id,
                        Reminder.status == ReminderStatus.SCHEDULED.value,
                    )
                )
            ).all()
            ts = now or self._now()
            for r in rows:
                r.status = ReminderStatus.CANCELLED.value
                r.updated_at = ts
            await session.commit()
            return len(rows)

    async def delete_for_task(self, task_id: int) -> int:
        """HARD-delete all reminder rows of a task (FK-safe: called by
        TaskService.delete BEFORE deleting the task row). Returns count."""
        async with self._sf() as session:
            rows = (
                await session.scalars(
                    select(Reminder).where(Reminder.task_id == task_id)
                )
            ).all()
            for r in rows:
                await session.delete(r)
            await session.commit()
            return len(rows)

    async def mark_fired(self, reminder_id: int, *, run_at: datetime, error: str | None = None) -> Reminder:
        async with self._sf() as session:
            row = await session.get(Reminder, reminder_id)
            if row is None:
                raise NotFoundError(f"reminder {reminder_id} not found")
            row.status = ReminderStatus.FIRED.value
            row.last_run = run_at.astimezone(timezone.utc)
            row.error = error
            row.updated_at = run_at.astimezone(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def mark_cancelled(self, reminder_id: int, *, now: datetime) -> Reminder:
        async with self._sf() as session:
            row = await session.get(Reminder, reminder_id)
            if row is None:
                raise NotFoundError(f"reminder {reminder_id} not found")
            row.status = ReminderStatus.CANCELLED.value
            row.updated_at = now.astimezone(timezone.utc)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_all(self) -> list[Reminder]:
        async with self._sf() as session:
            return list((await session.scalars(select(Reminder).order_by(Reminder.id))).all())


class ProviderConfigRepository(_BaseRepo[ProviderConfig]):
    async def create(
        self,
        *,
        name: str,
        provider_type: str = "openai_compatible",
        base_url: str,
        model: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        timeout_s: float = 30.0,
        secret_reference: str | None = None,
        enabled: bool = True,
    ) -> ProviderConfig:
        # M2a.1-F / M2a.2-B: validate BEFORE persistence (shared canonical rules)
        validate_secret_reference(secret_reference)
        validate_provider_config_numeric(
            timeout_s=timeout_s,
            max_tokens=max_tokens,
            max_context_tokens=max_context_tokens,
            temperature=temperature,
        )
        now = self._now()
        async with self._sf() as session:
            cfg = ProviderConfig(
                name=name,
                provider_type=provider_type,
                base_url=base_url,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                max_context_tokens=max_context_tokens,
                timeout_s=timeout_s,
                secret_reference=secret_reference,
                enabled=enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(cfg)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise DuplicateError(f"provider name already exists: {name!r}") from None
            await session.refresh(cfg)
            return cfg

    async def get(self, provider_id: int) -> ProviderConfig:
        async with self._sf() as session:
            cfg = await session.get(ProviderConfig, provider_id)
            if cfg is None:
                raise NotFoundError(f"provider config {provider_id} not found")
            return cfg

    async def list_enabled(self) -> list[ProviderConfig]:
        async with self._sf() as session:
            return list(
                (await session.scalars(select(ProviderConfig).where(ProviderConfig.enabled))).all()
            )

    async def set_enabled(self, provider_id: int, enabled: bool) -> ProviderConfig:
        now = self._now()
        async with self._sf() as session:
            cfg = await session.get(ProviderConfig, provider_id)
            if cfg is None:
                raise NotFoundError(f"provider config {provider_id} not found")
            cfg.enabled = enabled
            cfg.updated_at = now
            await session.commit()
            await session.refresh(cfg)
            return cfg
