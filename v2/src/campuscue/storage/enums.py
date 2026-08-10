"""Canonical domain enums (ADR-012-A: TaskStatus single source of truth)."""

from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    """Closed set of task lifecycle states (ADR-012-A)."""

    PENDING_CONFIRM = "pending_confirm"  # extracted, low confidence, needs confirmation
    PENDING = "pending"  # accepted normal open task
    DONE = "done"  # completed
    DISMISSED = "dismissed"  # rejected/ignored but still participates in dedup history


class TaskCategory(str, Enum):
    HOMEWORK = "homework"
    EXAM = "exam"
    COMPETITION = "competition"
    ACTIVITY = "activity"
    NOTICE = "notice"
    OTHER = "other"


class TaskPriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


class ExtractionStatus(str, Enum):
    """Outcome of one extraction attempt (closed set)."""

    SUCCESS = "success"
    SKIPPED = "skipped"
    ERROR = "error"
    DUPLICATE = "duplicate"
