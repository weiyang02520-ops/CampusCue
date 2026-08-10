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
from campuscue.storage.enums import ExtractionStatus, TaskCategory, TaskPriority, TaskStatus
from campuscue.storage.models import Extraction, ProviderConfig, Source, Task

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

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Task]:
        async with self._sf() as session:
            return list(
                (
                    await session.scalars(
                        select(Task).order_by(Task.created_at.desc()).limit(limit).offset(offset)
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
