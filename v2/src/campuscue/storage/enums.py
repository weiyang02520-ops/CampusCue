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


class ReminderType(str, Enum):
    """Reminder intent types (M3). Closed set enforced at repository + DB."""

    DAY_BEFORE = "day_before"  # deadline - 1 day
    HOURS_BEFORE = "hours_before"  # deadline - 2 hours
    DEADLINE = "deadline"  # at deadline moment


class ReminderStatus(str, Enum):
    """Reminder fact lifecycle (M3). DB rows are canonical facts."""

    SCHEDULED = "scheduled"  # active, has a derived scheduler job
    FIRED = "fired"  # delivered at least once
    CANCELLED = "cancelled"  # task lifecycle cancelled the reminder
