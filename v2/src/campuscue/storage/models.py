"""Storage ORM models (SQLAlchemy 2.x, M2a scope).

Tables: sources, tasks, extractions, provider_configs, schema_meta.
Explicitly NOT implemented: reminders, messages, settings (YAGNI).
All datetimes cross the storage boundary as timezone-aware UTC (ADR-012-G).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA_VERSION = 1


class UTCDateTime(TypeDecorator):
    """SQLite does not preserve tzinfo. Canonical storage is UTC (ADR-012-G):

    - write: aware datetime is normalized to UTC (naive REJECTED)
    - read:  always returns a timezone-aware UTC datetime
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(f"naive datetime rejected at storage boundary: {value!r}")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)

from campuscue.storage.enums import ExtractionStatus, TaskCategory, TaskPriority, TaskStatus


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(value: datetime) -> datetime:
    """Enforce ADR-012-G: naive datetime at the domain boundary is REJECTED."""
    if value.tzinfo is None:
        raise ValueError(f"naive datetime rejected at storage boundary: {value!r}")
    return value.astimezone(timezone.utc)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("platform", "conversation_id", name="uq_source_platform_conversation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    auto_extract: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    context_window: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    privacy_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        # First-version safeguard (ADR-012, §22): at most one Task per
        # (source, source_message_id) — the M2 extraction schema creates at most
        # one Task from one source message.
        UniqueConstraint("source_id", "source_message_id", name="uq_task_source_message"),
        Index("ix_task_dedup_key", "dedup_key"),
        # DB-level closed-set defense (M2a.1-C): repository is not the only writer
        CheckConstraint("status IN ('pending_confirm','pending','done','dismissed')", name="ck_task_status"),
        CheckConstraint("category IN ('homework','exam','competition','activity','notice','other')", name="ck_task_category"),
        CheckConstraint("priority IN ('high','normal','low')", name="ck_task_priority"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskCategory.OTHER.value)
    course: Mapped[str | None] = mapped_column(String(128), nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.PENDING.value)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default=TaskPriority.NORMAL.value)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    dedup_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_text_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class Extraction(Base):
    __tablename__ = "extractions"
    __table_args__ = (
        CheckConstraint("status IN ('success','skipped','error','duplicate')", name="ck_extraction_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id"), nullable=True)
    source_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ExtractionStatus.SUCCESS.value
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    # raw model output may contain private content: local DB only, never logs
    raw_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    # structured audit JSON: {"l1":{}, "l3":{}, "l4":{}, "l5":{}, "outcome":{}}
    audit: Mapped[str | None] = mapped_column(Text, nullable=True)
    # safe/redacted error text only (never keys/headers/raw provider bodies)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=_utcnow)


class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_provider_name"),
        CheckConstraint("timeout_s > 0", name="ck_provider_timeout"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False, default="openai_compatible")
    base_url: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_context_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_s: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    # only the ENV VARIABLE NAME; the secret value never enters the DB
    secret_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, default=_utcnow, onupdate=_utcnow
    )


class SchemaMeta(Base):
    __tablename__ = "schema_meta"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


def store_audit(audit: dict[str, Any]) -> str:
    return json.dumps(audit, ensure_ascii=False, sort_keys=True)


def load_audit(raw: str | None) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
