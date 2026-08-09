"""SQLModel tables for CampusAgent.

Timezone convention follows the AstrBot core (``astrbot/core/db/po.py``): every
datetime column stores a timezone-aware UTC value. Wall-clock rendering happens
at the presentation layer using ``CAMPUS_TIMEZONE``. Deadlines are the one place
where this matters a lot -- "周五晚上12点" is a wall-clock statement made in
Asia/Shanghai, so the resolver converts to UTC once, at extraction time, and
everything downstream compares UTC to UTC.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import JSON, Field, SQLModel, Text

CAMPUS_TIMEZONE = "Asia/Shanghai"
"""Wall-clock timezone for interpreting and rendering campus deadlines."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    """Re-attach UTC to a datetime read back from SQLite.

    SQLite has no timezone type, so SQLAlchemy hands back naive datetimes even
    though timezone-aware UTC values went in. Calling ``astimezone`` on one of
    those makes Python assume it is *local* time, which silently shifts every
    deadline by the local offset -- an 8-hour error in China, enough to turn
    "Friday 23:59" into "Friday 15:59" on the task card.

    Every read path must funnel datetimes through here before formatting or
    comparing them.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class CampusTimestampMixin(SQLModel):
    """Mirrors ``astrbot.core.db.po.TimestampMixin`` so both halves of the
    schema behave identically under ``SQLModel.metadata.create_all``."""

    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(
        default_factory=_utcnow,
        sa_column_kwargs={"onupdate": _utcnow},
    )


# --- task lifecycle -------------------------------------------------------
# pending_confirm : extracted, but confidence below threshold -- waits for the
#                   student to accept or reject it. Still gets reminders: an
#                   unconfirmed task has a real deadline, and staying silent
#                   until someone notices the queue defeats the point
#                   (reminders.py schedules for it like active).
# active          : a real task. Reminders are scheduled.
# done            : finished. Any pending reminder is cancelled.
# dismissed       : the student said this is not a task. Kept, not deleted, so
#                   the dedup key still blocks a re-extraction of the same
#                   message and so the false-positive rate stays measurable.
TASK_STATUSES = ("pending_confirm", "active", "done", "dismissed")

# Deliberately small and closed. A vague "other" bucket would let the model
# dump anything it did not understand into the task list, which is exactly the
# failure mode the confidence gate exists to prevent.
TASK_TYPES = ("homework", "exam", "competition", "activity", "notice")


class CampusTask(CampusTimestampMixin, SQLModel, table=True):
    """One actionable affair extracted from a message, or created by hand."""

    __tablename__: str = "campus_tasks"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    task_id: str = Field(
        max_length=64,
        nullable=False,
        unique=True,
        default_factory=_new_id,
    )

    # Owner. A unified message origin (see astrbot MessageSession), which is
    # also the address a reminder gets pushed back to.
    umo: str = Field(max_length=255, nullable=False, index=True)

    title: str = Field(max_length=255, nullable=False)
    task_type: str = Field(max_length=32, nullable=False)
    status: str = Field(default="active", max_length=32, index=True)

    # UTC. Nullable because some notices are genuinely undated ("下周交，具体
    # 时间待通知") and dropping them would lose real information.
    deadline: datetime | None = Field(default=None, index=True)
    deadline_is_explicit: bool = Field(default=True)
    """False when the deadline was inferred rather than stated, e.g. a bare
    date with no time got defaulted to 23:59. Surfaced in the UI so the student
    knows which part the model guessed."""

    location: str | None = Field(default=None, max_length=255)
    items: list = Field(default_factory=list, sa_type=JSON)
    """Things to bring. The exam scenario ("带身份证校园卡") is the reason this
    is a first-class column instead of prose in the description."""
    detail: str | None = Field(default=None, sa_type=Text)

    # --- provenance: the answer to "what if the AI made this up" ----------
    confidence: float = Field(default=1.0)
    source_kind: str = Field(default="extracted", max_length=32)
    """extracted | manual | replay -- so the demo can prove which path ran."""
    source_umo: str | None = Field(default=None, max_length=255)
    source_group_name: str | None = Field(default=None, max_length=255)
    source_sender_name: str | None = Field(default=None, max_length=255)
    source_message_id: str | None = Field(default=None, max_length=128, index=True)
    source_sent_at: datetime | None = Field(default=None)
    """When the original message was sent (UTC). This is the base for resolving
    relative expressions, so it must be kept, not just the extraction time."""
    raw_text: str | None = Field(default=None, sa_type=Text)
    extract_reason: str | None = Field(default=None, sa_type=Text)
    """The model's own stated justification, shown verbatim in the trace panel."""
    dedup_key: str = Field(default="", max_length=128, index=True)

    # --- reminders --------------------------------------------------------
    reminder_job_ids: list = Field(default_factory=list, sa_type=JSON)
    """Cron job ids owned by this task. A list because a task can carry more
    than one reminder (e.g. T-1day and T-2h). Cancelled on done/dismissed and
    rebuilt when the deadline is edited."""
    reminded_at: datetime | None = Field(default=None)


# --- extraction audit -----------------------------------------------------
# Only messages that clear L1 get a row. Logging every rejected chatter message
# would turn a busy group into tens of thousands of rows a day and the interesting
# signal -- what did the model see, and why did it decide that -- is all
# post-L1 anyway. L1 rejections are counted in aggregate instead (see
# CampusSource.stat_* columns) so the "we filter 90% for free" claim stays
# measurable without storing the group's entire chat history.
EXTRACTION_OUTCOMES = (
    "task_created",
    "pending_confirm",
    "model_said_none",
    "duplicate",
    "llm_error",
    "parse_error",
    "deadline_rejected",
)


class CampusExtraction(CampusTimestampMixin, SQLModel, table=True):
    """One extraction attempt on one message. The trace shown in the UI."""

    __tablename__: str = "campus_extractions"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    extraction_id: str = Field(
        max_length=64,
        nullable=False,
        unique=True,
        default_factory=_new_id,
    )

    umo: str = Field(max_length=255, nullable=False, index=True)
    source_message_id: str | None = Field(default=None, max_length=128, index=True)
    task_id: str | None = Field(default=None, max_length=64, index=True)
    """Set when this attempt produced a task, so the board can show the trace."""

    outcome: str = Field(max_length=32, nullable=False, index=True)
    raw_text: str = Field(default="", sa_type=Text)
    message_sent_at: datetime | None = Field(default=None)

    # L1
    l1_score: float = Field(default=0.0)
    l1_hits: dict = Field(default_factory=dict, sa_type=JSON)
    """Which rules fired, e.g. {"keywords": ["提交"], "time": ["周五","12点"],
    "sender_role": "admin"}. Rendered as the first step of the trace."""

    # L2
    l2_model: str | None = Field(default=None, max_length=128)
    l2_raw_response: str | None = Field(default=None, sa_type=Text)
    """Kept verbatim. When the model returns something unparseable this is the
    only way to find out why, and on stage it is the proof that the JSON is the
    model's own output and not a hardcoded fixture."""
    l2_parsed: dict = Field(default_factory=dict, sa_type=JSON)
    l2_latency_ms: int | None = Field(default=None)
    l2_prompt_tokens: int | None = Field(default=None)
    l2_completion_tokens: int | None = Field(default=None)

    # L3
    l3_resolved_deadline: datetime | None = Field(default=None)
    l3_notes: dict = Field(default_factory=dict, sa_type=JSON)
    """How the deadline was resolved and whether code and model agreed, e.g.
    {"phrase": "周五晚上12点", "code": "...", "model": "...", "agreed": false,
     "winner": "code"}."""

    error: str | None = Field(default=None, sa_type=Text)


SOURCE_TYPES = ("course", "competition", "admin", "club", "other")
"""What kind of group this is. Unlike ``TASK_TYPES`` this one keeps an "other"
bucket: the student is declaring it by hand, so a wrong guess is theirs to make
and costs nothing downstream."""


class CampusSource(CampusTimestampMixin, SQLModel, table=True):
    """A watched group, and what it is about.

    Knowing that a group is "软件工程课程群" is worth real accuracy: it tells the
    model which course a bare "实验三" belongs to, and it lets the board group
    tasks by course. Also carries the per-group L1 counters that back the
    "filtered N% for zero tokens" claim.
    """

    __tablename__: str = "campus_sources"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    umo: str = Field(max_length=255, nullable=False, unique=True, index=True)

    display_name: str | None = Field(default=None, max_length=255)
    course_name: str | None = Field(default=None, max_length=255)
    source_type: str = Field(default="course", max_length=32)
    """course | competition | admin | club | other"""
    enabled: bool = Field(default=True)
    """A watched group can be muted without losing its history or mapping."""

    authority_senders: list = Field(default_factory=list, sa_type=JSON)
    """Sender ids treated as authoritative (teacher, monitor). Raises the L1
    score -- a teacher saying "周五交" matters more than a classmate saying it."""

    stat_seen: int = Field(default=0)
    stat_l1_passed: int = Field(default=0)
    stat_tasks_created: int = Field(default=0)


class CampusProfile(CampusTimestampMixin, SQLModel, table=True):
    """Per-student reminder preferences."""

    __tablename__: str = "campus_profiles"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    umo: str = Field(max_length=255, nullable=False, unique=True, index=True)

    display_name: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default=CAMPUS_TIMEZONE, max_length=64)

    lead_minutes: dict = Field(
        default_factory=lambda: {
            # Per type, in minutes before the deadline. Exams get an earlier
            # nudge because the failure mode is worse and often involves
            # bringing something (id card, student card).
            "homework": [1440, 120],
            "exam": [2880, 720],
            "competition": [4320, 1440],
            "activity": [1440],
            "notice": [1440],
        },
        sa_type=JSON,
    )

    quiet_hours: dict = Field(
        default_factory=lambda: {"start": "23:00", "end": "07:30"},
        sa_type=JSON,
    )
    """Wall-clock quiet window in the profile timezone. A reminder that would
    land inside it slides to the end of the window -- unless the deadline itself
    falls inside, in which case it fires early rather than late."""

    confidence_threshold: float = Field(default=0.7)
    """Below this an extraction becomes pending_confirm instead of a live task."""

    auto_confirm: bool = Field(default=False)
    """Demo/debug switch: skip the confirmation queue entirely."""


class CampusSetting(CampusTimestampMixin, SQLModel, table=True):
    """Process-wide settings, one row per key.

    Deliberately not folded into ``CampusProfile``: a profile is per-umo, and the
    things stored here are singular by nature. "Where do notifications go" has
    exactly one answer -- the student's own chat -- and storing it per group would
    mean twelve groups can disagree about where the student is.

    A key/value table rather than a one-row table so adding a setting never needs
    a schema migration, which matters because ``create_all`` does not run ALTERs.
    """

    __tablename__: str = "campus_settings"

    id: int | None = Field(
        default=None,
        primary_key=True,
        sa_column_kwargs={"autoincrement": True},
    )
    key: str = Field(max_length=64, nullable=False, unique=True, index=True)
    value: dict = Field(default_factory=dict, sa_type=JSON)
    """Wrapped in an object ({"v": ...}) so scalars, lists and dicts all fit the
    same JSON column."""


__all__ = [
    "CAMPUS_TIMEZONE",
    "EXTRACTION_OUTCOMES",
    "as_utc",
    "SOURCE_TYPES",
    "TASK_STATUSES",
    "TASK_TYPES",
    "CampusExtraction",
    "CampusProfile",
    "CampusSetting",
    "CampusSource",
    "CampusTask",
    "CampusTimestampMixin",
]
