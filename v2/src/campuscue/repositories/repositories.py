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

from sqlalchemy import func, or_, select
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
    Setting,
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


class SettingRepository(_BaseRepo[Setting]):
    """Single-row-per-key settings persistence (M5). Values are JSON-safe dicts."""

    async def get(self, key: str) -> Setting | None:
        async with self._sf() as session:
            return await session.get(Setting, key)

    async def set(self, key: str, value: dict) -> Setting:
        now = self._now()
        async with self._sf() as session:
            row = await session.get(Setting, key)
            if row is None:
                row = Setting(key=key, value=value, updated_at=now)
                session.add(row)
            else:
                row.value = value
                row.updated_at = now
            await session.commit()
            await session.refresh(row)
            return row

    async def list_all(self) -> list[Setting]:
        async with self._sf() as session:
            return list((await session.scalars(select(Setting).order_by(Setting.key))).all())


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

    async def list_all(self, *, include_deleted: bool = False) -> list[Source]:
        async with self._sf() as session:
            stmt = select(Source).order_by(Source.id)
            if not include_deleted:
                stmt = stmt.where(Source.deleted_at.is_(None))
            return list((await session.scalars(stmt)).all())

    async def update(
        self,
        source_id: int,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        auto_extract: bool | None = None,
        context_window: int | None = None,
        privacy_policy: str | None = None,
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
            if privacy_policy is not None:
                source.privacy_policy = privacy_policy
            source.updated_at = now
            await session.commit()
            await session.refresh(source)
            return source

    async def soft_delete(self, source_id: int) -> Source:
        """M5 source delete: mark deleted_at instead of hard-deleting so
        Task/Extraction provenance rows keep a valid FK reference."""
        now = self._now()
        async with self._sf() as session:
            source = await session.get(Source, source_id)
            if source is None:
                raise NotFoundError(f"source {source_id} not found")
            if source.deleted_at is not None:
                raise DuplicateError(f"source {source_id} is already deleted")
            source.deleted_at = now
            source.enabled = False
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

    async def count_filtered(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        course: str | None = None,
        source_id: int | None = None,
        deadline_from: datetime | None = None,
        deadline_to: datetime | None = None,
        q: str | None = None,
    ) -> int:
        stmt = self._filtered_stmt(
            status=status, category=category, course=course, source_id=source_id,
            deadline_from=deadline_from, deadline_to=deadline_to, q=q,
        )
        async with self._sf() as session:
            return await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    async def list_filtered(
        self,
        *,
        status: str | None = None,
        category: str | None = None,
        course: str | None = None,
        source_id: int | None = None,
        deadline_from: datetime | None = None,
        deadline_to: datetime | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        stmt = self._filtered_stmt(
            status=status, category=category, course=course, source_id=source_id,
            deadline_from=deadline_from, deadline_to=deadline_to, q=q,
        ).order_by(Task.created_at.desc()).limit(limit).offset(offset)
        async with self._sf() as session:
            return list((await session.scalars(stmt)).all())

    @staticmethod
    def _filtered_stmt(
        *,
        status: str | None = None,
        category: str | None = None,
        course: str | None = None,
        source_id: int | None = None,
        deadline_from: datetime | None = None,
        deadline_to: datetime | None = None,
        q: str | None = None,
    ):
        stmt = select(Task)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if category is not None:
            stmt = stmt.where(Task.category == category)
        if course is not None:
            stmt = stmt.where(Task.course == course)
        if source_id is not None:
            stmt = stmt.where(Task.source_id == source_id)
        if deadline_from is not None:
            stmt = stmt.where(Task.deadline >= deadline_from)
        if deadline_to is not None:
            stmt = stmt.where(Task.deadline <= deadline_to)
        if q:
            like = f"%{q}%"
            stmt = stmt.where(or_(Task.title.like(like), Task.course.like(like), Task.description.like(like)))
        return stmt

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
        description: str | None = None,
        category: str | None = None,
        course: str | None = None,
        deadline: datetime | object = _UNSET,
        priority: str | None = None,
        status: str | None = None,
    ) -> Task:
        """M4/M5 combined field update primitive (persistence only; reminder
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
            if description is not None:
                task.description = description
            if category is not None:
                task.category = _require_enum(TaskCategory, category, "category")
            if course is not None:
                task.course = course.strip() or None
            if deadline is not _UNSET:
                task.deadline = deadline.astimezone(timezone.utc) if deadline else None
            if priority is not None:
                task.priority = _require_enum(TaskPriority, priority, "priority")
            if status is not None:
                task.status = _require_enum(TaskStatus, status, "status")
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

    async def get(self, extraction_id: int) -> Extraction:
        async with self._sf() as session:
            row = await session.get(Extraction, extraction_id)
            if row is None:
                raise NotFoundError(f"extraction {extraction_id} not found")
            return row

    async def count_filtered(
        self,
        *,
        source_id: int | None = None,
        had_task: bool | None = None,
        confidence_min: float | None = None,
    ) -> int:
        stmt = self._filtered_stmt(source_id=source_id, had_task=had_task, confidence_min=confidence_min)
        async with self._sf() as session:
            return await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    async def list_filtered(
        self,
        *,
        source_id: int | None = None,
        had_task: bool | None = None,
        confidence_min: float | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Extraction]:
        stmt = (
            self._filtered_stmt(source_id=source_id, had_task=had_task, confidence_min=confidence_min)
            .order_by(Extraction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        async with self._sf() as session:
            return list((await session.scalars(stmt)).all())

    @staticmethod
    def _filtered_stmt(
        *,
        source_id: int | None = None,
        had_task: bool | None = None,
        confidence_min: float | None = None,
    ):
        stmt = select(Extraction)
        if source_id is not None:
            stmt = stmt.where(Extraction.source_id == source_id)
        if confidence_min is not None:
            stmt = stmt.where(Extraction.confidence >= confidence_min)
        if had_task is not None:
            # had_task is derived from normalized_result JSON; first version uses
            # status='success' as the practical proxy for "created/had a task".
            if had_task:
                stmt = stmt.where(Extraction.status == "success")
            else:
                stmt = stmt.where(Extraction.status != "success")
        return stmt


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

    async def count_filtered(self, *, status: str | None = None, task_id: int | None = None) -> int:
        stmt = self._filtered_stmt(status=status, task_id=task_id)
        async with self._sf() as session:
            return await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    async def list_filtered(
        self,
        *,
        status: str | None = None,
        task_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Reminder]:
        stmt = (
            self._filtered_stmt(status=status, task_id=task_id)
            .order_by(Reminder.trigger_at)
            .limit(limit)
            .offset(offset)
        )
        async with self._sf() as session:
            return list((await session.scalars(stmt)).all())

    @staticmethod
    def _filtered_stmt(*, status: str | None = None, task_id: int | None = None):
        stmt = select(Reminder)
        if status is not None:
            stmt = stmt.where(Reminder.status == status)
        if task_id is not None:
            stmt = stmt.where(Reminder.task_id == task_id)
        return stmt


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

    async def list_all(self) -> list[ProviderConfig]:
        async with self._sf() as session:
            return list((await session.scalars(select(ProviderConfig).order_by(ProviderConfig.id))).all())

    async def update(
        self,
        provider_id: int,
        *,
        name: str | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        timeout_s: float | None = None,
        secret_reference: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderConfig:
        now = self._now()
        async with self._sf() as session:
            cfg = await session.get(ProviderConfig, provider_id)
            if cfg is None:
                raise NotFoundError(f"provider config {provider_id} not found")
            if name is not None:
                cfg.name = name
            if provider_type is not None:
                cfg.provider_type = provider_type
            if base_url is not None:
                cfg.base_url = base_url
            if model is not None:
                cfg.model = model
            if temperature is not None:
                cfg.temperature = temperature
            if max_tokens is not None:
                cfg.max_tokens = max_tokens
            if max_context_tokens is not None:
                cfg.max_context_tokens = max_context_tokens
            if timeout_s is not None:
                cfg.timeout_s = timeout_s
            if secret_reference is not None:
                validate_secret_reference(secret_reference)
                cfg.secret_reference = secret_reference
            if enabled is not None:
                cfg.enabled = enabled
            # Re-run numeric validation on the merged config before commit.
            validate_provider_config_numeric(
                timeout_s=cfg.timeout_s,
                max_tokens=cfg.max_tokens,
                max_context_tokens=cfg.max_context_tokens,
                temperature=cfg.temperature,
            )
            cfg.updated_at = now
            await session.commit()
            await session.refresh(cfg)
            return cfg

    async def delete(self, provider_id: int) -> None:
        async with self._sf() as session:
            cfg = await session.get(ProviderConfig, provider_id)
            if cfg is None:
                raise NotFoundError(f"provider config {provider_id} not found")
            await session.delete(cfg)
            await session.commit()

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
