"""Wire shapes for the task board.

Datetimes go out as UTC ISO-8601 with an explicit offset and the board renders
them in campus time. Sending naive strings is how the 8-hour bug in ``as_utc``
would come back through a different door.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from campuscue.models import (
    SOURCE_TYPES,
    TASK_STATUSES,
    TASK_TYPES,
    CampusExtraction,
    CampusProfile,
    CampusSource,
    CampusTask,
    as_utc,
)

_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
"""Quiet hours are wall-clock strings, not datetimes: 23:00–07:30 means those
hours every night, and any date attached to them would be a lie."""


class TaskOut(BaseModel):
    """One card on the board."""

    task_id: str
    umo: str
    """Which group this belongs to. Needed because the SSE stream is global: once
    the board can be filtered to one source, an arriving event has to be
    attributable or a task from another group appears on a filtered board."""
    title: str
    task_type: str
    status: str

    deadline: datetime | None = None
    deadline_is_explicit: bool = True
    location: str | None = None
    items: list[str] = Field(default_factory=list)
    detail: str | None = None

    confidence: float
    source_kind: str
    source_group_name: str | None = None
    source_sender_name: str | None = None
    source_sent_at: datetime | None = None
    raw_text: str | None = None
    extract_reason: str | None = None

    has_reminder: bool = False
    created_at: datetime

    @classmethod
    def of(cls, task: CampusTask) -> TaskOut:
        return cls(
            task_id=task.task_id,
            umo=task.umo,
            title=task.title,
            task_type=task.task_type,
            status=task.status,
            deadline=as_utc(task.deadline),
            deadline_is_explicit=task.deadline_is_explicit,
            location=task.location,
            items=list(task.items or []),
            detail=task.detail,
            confidence=task.confidence,
            source_kind=task.source_kind,
            source_group_name=task.source_group_name,
            source_sender_name=task.source_sender_name,
            source_sent_at=as_utc(task.source_sent_at),
            raw_text=task.raw_text,
            extract_reason=task.extract_reason,
            has_reminder=bool(task.reminder_job_ids),
            created_at=as_utc(task.created_at),
        )


class TraceStep(BaseModel):
    """One tier of the extraction, for the "why did the AI decide this" panel."""

    tier: str
    """l1 | l2 | l3"""
    summary: str
    detail: dict = Field(default_factory=dict)


class TraceOut(BaseModel):
    """The full audit of one extraction attempt."""

    extraction_id: str
    outcome: str
    raw_text: str
    message_sent_at: datetime | None = None
    steps: list[TraceStep] = Field(default_factory=list)
    model: str | None = None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    raw_response: str | None = None
    error: str | None = None

    @classmethod
    def of(cls, row: CampusExtraction) -> TraceOut:
        hits = row.l1_hits or {}
        signals = [f"{k}={v}" for k, v in hits.items() if k != "score"]
        steps = [
            TraceStep(
                tier="l1",
                summary=(
                    f"规则预筛通过，得分 {row.l1_score:.1f}"
                    if row.l1_score
                    else "规则预筛"
                ),
                detail={"score": row.l1_score, "signals": signals, **hits},
            )
        ]

        parsed = row.l2_parsed or {}
        if parsed:
            if parsed.get("is_task"):
                summary = (
                    f"模型判定为 {parsed.get('task_type') or '事务'}，"
                    f"置信度 {parsed.get('confidence', 0):.2f}"
                )
            else:
                summary = "模型判定为非事务"
            steps.append(TraceStep(tier="l2", summary=summary, detail=parsed))

        notes = row.l3_notes or {}
        if notes:
            phrase = notes.get("phrase")
            resolved = as_utc(row.l3_resolved_deadline)
            if resolved and phrase:
                summary = f"“{phrase}” 由程序换算为 {resolved:%Y-%m-%d %H:%M}Z"
            elif phrase:
                summary = (
                    f"“{phrase}” 无法换算（{notes.get('note') or notes.get('basis')}）"
                )
            else:
                summary = "未提及时间"
            steps.append(
                TraceStep(
                    tier="l3",
                    summary=summary,
                    detail={
                        **notes,
                        "resolved": resolved.isoformat() if resolved else None,
                    },
                )
            )

        return cls(
            extraction_id=row.extraction_id,
            outcome=row.outcome,
            raw_text=row.raw_text,
            message_sent_at=as_utc(row.message_sent_at),
            steps=steps,
            model=row.l2_model,
            latency_ms=row.l2_latency_ms,
            prompt_tokens=row.l2_prompt_tokens,
            completion_tokens=row.l2_completion_tokens,
            raw_response=row.l2_raw_response,
            error=row.error,
        )


class TaskDetailOut(BaseModel):
    """A task plus its provenance."""

    task: TaskOut
    trace: list[TraceOut] = Field(default_factory=list)


class StatsOut(BaseModel):
    """Header numbers. ``l1_filtered_ratio`` is the measured proof of the
    "most traffic costs nothing" claim, not an assertion."""

    total_active: int = 0
    total_pending_confirm: int = 0
    due_today: int = 0
    due_this_week: int = 0
    overdue: int = 0
    messages_seen: int = 0
    messages_through_l1: int = 0
    tasks_created: int = 0
    l1_filtered_ratio: float = 0.0


class UpdateTaskIn(BaseModel):
    """Fields a student may correct.

    Editing matters as much as tracing: showing why the AI decided something is
    only half an answer to "what if it is wrong" -- the other half is being able
    to fix it.
    """

    title: str | None = None
    deadline: datetime | None = None
    location: str | None = None
    items: list[str] | None = None
    detail: str | None = None
    task_type: str | None = None


class CreateTaskIn(BaseModel):
    """A task typed in by hand rather than extracted."""

    title: str
    task_type: str = "notice"
    deadline: datetime | None = None
    location: str | None = None
    items: list[str] = Field(default_factory=list)
    detail: str | None = None


class SourceOut(BaseModel):
    """One watched group, for the board's source picker.

    ``label`` is resolved server-side through display_name → course_name → a
    readable form of the umo, so the frontend never has to know that a umo looks
    like ``aiocqhttp:GroupMessage:7788``. ``display_name`` is carried separately
    so the settings panel can show what the student actually typed -- and detect
    an empty field as "clear it" -- instead of echoing the fallback label.
    """

    umo: str
    label: str
    display_name: str | None = None
    course_name: str | None = None
    source_type: str = "course"
    enabled: bool = True
    open_tasks: int = 0
    messages_seen: int = 0

    @classmethod
    def of(cls, source: CampusSource, open_tasks: int = 0) -> SourceOut:
        return cls(
            umo=source.umo,
            label=source.display_name or source.course_name or short_umo(source.umo),
            display_name=source.display_name,
            course_name=source.course_name,
            source_type=source.source_type,
            enabled=source.enabled,
            open_tasks=open_tasks,
            messages_seen=source.stat_seen,
        )


class UpdateSourceIn(BaseModel):
    """What a student may declare about a watched group.

    ``course_name`` is the one that changes model behaviour rather than only the
    label: ``build_user_message`` renders it as 对应课程 in the L2 prompt, so
    naming a group turns "周五前交" into "软件工程 周五前交" for the extractor.
    """

    display_name: str | None = None
    course_name: str | None = None
    source_type: str | None = None
    enabled: bool | None = None

    @field_validator("source_type")
    @classmethod
    def _known_type(cls, value: str | None) -> str | None:
        if value is not None and value not in SOURCE_TYPES:
            raise ValueError(f"source_type 必须是 {'/'.join(SOURCE_TYPES)} 之一")
        return value


class DeleteSourceOut(BaseModel):
    """What a group deletion actually removed.

    Reports counts rather than returning 204: the button exists to clear fixture
    groups out of a demo database, and "deleted" with no numbers gives the student
    no way to tell a working delete from a no-op on a mistyped umo.
    """

    umo: str
    tasks: int = 0
    extractions: int = 0
    reminders_cancelled: int = 0


class NotifyTargetOut(BaseModel):
    """One place a detection could be sent, offered in the panel's picker.

    Resolved server-side rather than typed by the student: a umo is a
    platform-internal string, and one wrong character produces a setting that
    saves cleanly and then never delivers anything.
    """

    umo: str
    label: str
    hint: str = ""
    recommended: bool = False


class NotifyOut(BaseModel):
    """Where detections go, and through which channels.

    Global rather than per-group -- see ``campuscue.models.CampusSetting``.
    ``target_label`` is resolved server-side so the panel can show 我的QQ私聊
    instead of ``qq:FriendMessage:20002``.
    """

    target_umo: str = ""
    target_label: str = ""
    on_detect: bool = True
    desktop_toast: bool = True
    deadline_reminders: bool = True
    toast_supported: bool = True
    """False off Windows, so the panel can explain why the switch does nothing."""
    candidates: list[NotifyTargetOut] = Field(default_factory=list)
    """Everything the picker can offer, in one response with the current values --
    a second request would let the picker and the selection disagree while the
    student is looking at them."""
    friend_umo_prefix: str = ""
    """What to put in front of a QQ number to address a private chat, e.g.
    ``qq:FriendMessage:``. The student's own uin is the one thing this process
    cannot discover -- the only account it knows is the bot's -- so the panel asks
    for the number and builds the umo from this instead of guessing."""


class UpdateNotifyIn(BaseModel):
    """Edits from the settings panel. Only the sent keys are written."""

    target_umo: str | None = None
    on_detect: bool | None = None
    desktop_toast: bool | None = None
    deadline_reminders: bool | None = None

    @field_validator("target_umo")
    @classmethod
    def _looks_like_a_umo(cls, value: str | None) -> str | None:
        """Reject a target that could never deliver.

        A malformed umo saves cleanly and then fails silently at push time, which
        is the one failure this product cannot afford -- the student would believe
        notifications are on. Empty is allowed and means "not chosen yet".
        """
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return ""
        parts = cleaned.split(":")
        if len(parts) < 3 or not all(parts[:3]):
            raise ValueError(
                "会话地址格式应为 平台:消息类型:号码，例如 qq:FriendMessage:10001"
            )
        return cleaned


class NotifyTestOut(BaseModel):
    """Result of the 试一下 button: one fake detection through the real path.

    Both channels are reported separately because they fail independently -- a
    toast can appear on the laptop while no QQ account is attached, and that is a
    useful thing to learn before a live demo rather than during one.
    """

    pushed: bool = False
    toasted: bool = False
    target: str = ""
    preview: str = ""
    detail: str = ""


class ProfileOut(BaseModel):
    """Reminder preferences for one group."""

    umo: str
    lead_minutes: dict[str, list[int]] = Field(default_factory=dict)
    quiet_hours: dict[str, str] = Field(default_factory=dict)
    confidence_threshold: float = 0.7
    auto_confirm: bool = False

    @classmethod
    def of(cls, profile: CampusProfile) -> ProfileOut:
        # The lead_minutes column is user-editable JSON; a dirty value must not
        # 500 the profile endpoint. Mirrors plan_reminders' tolerance.
        leads: dict[str, list[int]] = {}
        for k, v in (profile.lead_minutes or {}).items():
            if not isinstance(v, list):
                continue
            clean = [int(m) for m in v if isinstance(m, (int, float))]
            if clean:
                leads[str(k)] = clean
        return cls(
            umo=profile.umo,
            lead_minutes=leads,
            quiet_hours={
                str(k): str(v) for k, v in (profile.quiet_hours or {}).items()
            },
            confidence_threshold=profile.confidence_threshold,
            auto_confirm=profile.auto_confirm,
        )


class UpdateProfileIn(BaseModel):
    """Preference edits.

    Validated here rather than in the route because a malformed lead list does
    not fail loudly downstream -- ``plan_reminders`` would simply schedule
    nothing, and a reminder that silently never fires is the one bug this product
    cannot afford.
    """

    lead_minutes: dict[str, list[int]] | None = None
    quiet_hours: dict[str, str] | None = None
    confidence_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    auto_confirm: bool | None = None

    @field_validator("lead_minutes")
    @classmethod
    def _sane_leads(
        cls, value: dict[str, list[int]] | None
    ) -> dict[str, list[int]] | None:
        if value is None:
            return None
        cleaned: dict[str, list[int]] = {}
        for task_type, leads in value.items():
            if task_type not in TASK_TYPES:
                raise ValueError(f"未知任务类型 {task_type}")
            for lead in leads:
                # A week is already earlier than any student plans; a zero or
                # negative lead would fire at or after the deadline.
                if not 1 <= lead <= 20160:
                    raise ValueError("提前量需在 1 分钟到 14 天之间")
            # Sorted descending and de-duplicated: the earliest alarm first is
            # the order the evidence list renders, and two identical leads would
            # push the same text twice.
            cleaned[task_type] = sorted(set(leads), reverse=True)
        return cleaned

    @field_validator("quiet_hours")
    @classmethod
    def _sane_quiet(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if set(value) != {"start", "end"}:
            raise ValueError("免打扰时段需要 start 和 end")
        for key in ("start", "end"):
            if not _HHMM.fullmatch(value[key]):
                raise ValueError(f"{key} 需为 HH:MM")
        return {"start": value["start"], "end": value["end"]}


def short_umo(umo: str) -> str:
    """A umo a human can read.

    ``aiocqhttp:GroupMessage:7788`` becomes ``QQ群 7788``, and
    ``qq:FriendMessage:20002`` becomes ``QQ私聊 20002``. Falls back to the raw
    string for shapes this does not recognise rather than guessing, because a
    mislabelled group is worse than an ugly one -- the label is what a student
    uses to decide whose deadlines they are looking at.
    """
    parts = umo.split(":")
    if len(parts) < 3:
        return umo
    platform, kind, ident = parts[0], parts[1], parts[-1]
    # The message type matters as much as the platform now that a private chat is
    # selectable as the notify target: labelling qq:FriendMessage as 群 would tell
    # the student their reminders go somewhere they do not. Only applied to
    # platforms we actually recognise -- guessing that an unknown platform's
    # "GroupMessage" means the same thing is how a wrong label gets invented.
    kind_label = {"GroupMessage": "群", "FriendMessage": "私聊"}.get(kind, "")
    known = {"aiocqhttp": "QQ", "qq": "QQ", "webchat": "网页"}
    if platform in known:
        return f"{known[platform]}{kind_label} {ident}"
    return f"{platform} {ident}"


# --- import / export ------------------------------------------------------
#
# See campuscue/api/transfer.py for what travels and what deliberately does not.

TRANSFER_KIND = "campuscue.tasks"
"""Stamped into every export and required on import. A student will eventually
drop the wrong JSON file on this -- a browser bookmarks export, another tool's
backup -- and a named format lets the importer say so instead of reading a
hundred unrelated objects as tasks."""

TRANSFER_VERSION = 1


class TaskTransfer(BaseModel):
    """One task in the exchange format.

    Every identity and bookkeeping field is optional so the document can be
    written by hand: a title is the only thing a task genuinely cannot do without.
    ``task_id`` absent means "give it a new one", which is what a hand-written
    file wants, and ``umo`` absent falls back to the import target.
    """

    task_id: str | None = None
    umo: str = ""
    title: str
    task_type: str = "notice"
    status: str = "active"

    deadline: datetime | None = None
    deadline_is_explicit: bool = True
    location: str | None = None
    items: list[str] = Field(default_factory=list)
    detail: str | None = None

    confidence: float = 1.0
    source_kind: str = "import"
    source_umo: str | None = None
    source_group_name: str | None = None
    source_sender_name: str | None = None
    source_message_id: str | None = None
    source_sent_at: datetime | None = None
    raw_text: str | None = None
    extract_reason: str | None = None

    created_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def _has_a_title(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("任务标题不能为空")
        return cleaned

    @field_validator("task_type")
    @classmethod
    def _known_task_type(cls, value: str) -> str:
        # Rejected rather than coerced to "notice": a file whose types are all
        # wrong is a file for a different tool, and silently relabelling every
        # task would import it as a list of things that look right and are not.
        if value not in TASK_TYPES:
            raise ValueError(f"任务类型必须是 {'/'.join(TASK_TYPES)} 之一")
        return value

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str) -> str:
        if value not in TASK_STATUSES:
            raise ValueError(f"状态必须是 {'/'.join(TASK_STATUSES)} 之一")
        return value

    @field_validator("confidence")
    @classmethod
    def _sane_confidence(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("置信度需在 0 和 1 之间")
        return value


class ExportOut(BaseModel):
    """The whole document. ``count`` and ``umos`` are a summary of what follows,
    so the file says what it holds without being parsed in full."""

    kind: str = TRANSFER_KIND
    version: int = TRANSFER_VERSION
    exported_at: datetime
    count: int = 0
    umos: list[str] = Field(default_factory=list)
    tasks: list[TaskTransfer] = Field(default_factory=list)


class ImportIn(BaseModel):
    """An uploaded document, plus how to treat it.

    ``kind`` and ``version`` are validated rather than ignored: this endpoint
    writes tasks, and the cost of guessing at an unknown payload is a board full
    of garbage that has to be deleted by hand. ``kind`` is required (no default)
    so that arbitrary JSON that merely happens to contain a ``tasks`` array is
    rejected instead of silently accepted as a 课讯 export.
    """

    kind: str
    version: int = TRANSFER_VERSION
    tasks: list[TaskTransfer] = Field(default_factory=list)

    umo: str | None = None
    """Put every incoming task in this group, ignoring the umos in the file. What
    a student wants when moving a list between installs whose group ids differ --
    without it the tasks land on a board nothing points at."""

    overwrite: bool = False
    """Update tasks that are already here instead of skipping them."""

    @field_validator("kind")
    @classmethod
    def _right_kind(cls, value: str) -> str:
        if value != TRANSFER_KIND:
            raise ValueError(f"这不是课讯导出的文件（kind={value or '缺失'}）")
        return value

    @field_validator("version")
    @classmethod
    def _readable_version(cls, value: int) -> int:
        # Older is fine -- the format only ever gained optional fields. Newer is
        # not: it may carry meaning this build would drop on the floor.
        if value > TRANSFER_VERSION:
            raise ValueError(
                f"文件版本 {value} 比当前程序（{TRANSFER_VERSION}）新，先升级再导入"
            )
        return value


class ImportOut(BaseModel):
    """What the import did. Counted separately because the three outcomes mean
    different things: skipped is the safe default on a re-import, and reporting
    it as success would hide a file that changed nothing."""

    created: int = 0
    updated: int = 0
    skipped: int = 0
    reminders_planned: int = 0
    umos: list[str] = Field(default_factory=list)
    detail: str = ""


# --- full backup / restore -----------------------------------------------

BACKUP_KIND = "campuscue.backup"
BACKUP_VERSION = 1


class BackupTask(TaskTransfer):
    """Task state that belongs to CampusCue, excluding machine-local cron ids."""

    task_id: str = Field(min_length=1, max_length=64)
    umo: str = Field(min_length=1, max_length=255)
    updated_at: datetime | None = None
    reminded_at: datetime | None = None


class BackupSource(BaseModel):
    umo: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    course_name: str | None = Field(default=None, max_length=255)
    source_type: str = "course"
    enabled: bool = True
    authority_senders: list[str] = Field(default_factory=list, max_length=1000)
    stat_seen: int = Field(default=0, ge=0)
    stat_l1_passed: int = Field(default=0, ge=0)
    stat_tasks_created: int = Field(default=0, ge=0)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("source_type")
    @classmethod
    def _known_source_type(cls, value: str) -> str:
        if value not in SOURCE_TYPES:
            raise ValueError(f"source_type 必须是 {'/'.join(SOURCE_TYPES)} 之一")
        return value


class BackupProfile(BaseModel):
    umo: str = Field(min_length=1, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="Asia/Shanghai", min_length=1, max_length=64)
    lead_minutes: dict[str, list[int]] = Field(default_factory=dict)
    quiet_hours: dict[str, str] = Field(default_factory=dict)
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    auto_confirm: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("lead_minutes")
    @classmethod
    def _valid_leads(cls, value: dict[str, list[int]]) -> dict[str, list[int]]:
        return UpdateProfileIn._sane_leads(value) or {}

    @field_validator("quiet_hours")
    @classmethod
    def _valid_quiet(cls, value: dict[str, str]) -> dict[str, str]:
        return UpdateProfileIn._sane_quiet(value) or {}


class BackupSetting(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: dict = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BackupExtraction(BaseModel):
    extraction_id: str = Field(min_length=1, max_length=64)
    umo: str = Field(min_length=1, max_length=255)
    source_message_id: str | None = Field(default=None, max_length=128)
    task_id: str | None = Field(default=None, max_length=64)
    outcome: str
    raw_text: str = ""
    message_sent_at: datetime | None = None
    l1_score: float = 0.0
    l1_hits: dict = Field(default_factory=dict)
    l2_model: str | None = Field(default=None, max_length=128)
    l2_raw_response: str | None = None
    l2_parsed: dict = Field(default_factory=dict)
    l2_latency_ms: int | None = Field(default=None, ge=0)
    l2_prompt_tokens: int | None = Field(default=None, ge=0)
    l2_completion_tokens: int | None = Field(default=None, ge=0)
    l3_resolved_deadline: datetime | None = None
    l3_notes: dict = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("outcome")
    @classmethod
    def _known_outcome(cls, value: str) -> str:
        from campuscue.models import EXTRACTION_OUTCOMES

        if value not in EXTRACTION_OUTCOMES:
            raise ValueError(f"抽取结果必须是 {'/'.join(EXTRACTION_OUTCOMES)} 之一")
        return value


class BackupDocument(BaseModel):
    kind: str
    version: int
    exported_at: datetime
    tasks: list[BackupTask] = Field(default_factory=list, max_length=100000)
    sources: list[BackupSource] = Field(default_factory=list, max_length=10000)
    profiles: list[BackupProfile] = Field(default_factory=list, max_length=10000)
    settings: list[BackupSetting] = Field(default_factory=list, max_length=1000)
    extractions: list[BackupExtraction] = Field(default_factory=list, max_length=200000)


class BackupOut(BackupDocument):
    kind: str = BACKUP_KIND
    version: int = BACKUP_VERSION


class RestoreIn(BackupDocument):
    """A full replacement, guarded by format, version, uniqueness and consent."""

    confirm_replace: Literal[True]

    @field_validator("kind")
    @classmethod
    def _right_backup_kind(cls, value: str) -> str:
        if value != BACKUP_KIND:
            raise ValueError(f"这不是课讯完整备份（kind={value or '缺失'}）")
        return value

    @field_validator("version")
    @classmethod
    def _readable_backup_version(cls, value: int) -> int:
        if value > BACKUP_VERSION:
            raise ValueError(
                f"备份版本 {value} 比当前程序（{BACKUP_VERSION}）新，先升级再恢复"
            )
        if value < 1:
            raise ValueError("备份版本无效")
        return value

    @model_validator(mode="after")
    def _unique_identities(self):
        groups = (
            ("任务 ID", [row.task_id for row in self.tasks]),
            ("来源", [row.umo for row in self.sources]),
            ("群偏好", [row.umo for row in self.profiles]),
            ("设置键", [row.key for row in self.settings]),
            ("抽取 ID", [row.extraction_id for row in self.extractions]),
        )
        for label, values in groups:
            if len(values) != len(set(values)):
                raise ValueError(f"备份里有重复的{label}")
        return self


class RestoreOut(BaseModel):
    tasks: int = 0
    sources: int = 0
    profiles: int = 0
    settings: int = 0
    extractions: int = 0
    reminders: int = 0
    detail: str = ""


class ReminderOut(BaseModel):
    """One alarm currently on the scheduler."""

    job_id: str
    task_id: str
    task_title: str
    label: str
    """How this reminder was derived, e.g. "提前 1 天"."""
    fire_at: datetime | None = None
    status: str = "scheduled"


# --- setup / 接入 ---------------------------------------------------------
#
# The board's 接入与自检 page renders entirely from these. Deliberately a status
# document rather than a stream of log lines: every field below answers a
# question a student would otherwise answer by reading a terminal.


class CheckOut(BaseModel):
    """One readiness check, from ``provision.collect_checks``."""

    group: str
    """环境变量 / 配置文件 / 数据库 -- the section it renders under."""
    ok: bool
    text: str


class NapCatOut(BaseModel):
    """State of the local NapCat, mirroring ``campuscue.napcat.State``."""

    installed: bool = False
    home: str = ""
    running: bool = False
    pid: int | None = None
    managed: bool = False
    """We started it, so the stop button may act on it."""
    configured: bool = False
    ws_url: str = ""
    installing: bool = False
    supported: bool = True
    detail: str = ""
    accounts: list[str] = Field(default_factory=list)


class LinkOut(BaseModel):
    """Whether a QQ account is actually attached right now.

    Read from the adapter's live reverse-WS clients rather than from NapCat: a
    config file that looks right proves nothing, an open socket proves the whole
    chain. ``accounts`` are the uins that completed the handshake.
    """

    adapter_ready: bool = False
    """The aiocqhttp adapter is loaded and listening."""
    connected: bool = False
    accounts: list[str] = Field(default_factory=list)
    port: int = 0
    detail: str = ""


class SetupStatusOut(BaseModel):
    """Everything the 接入 page needs in one request.

    One endpoint rather than five because the page polls while a student watches:
    five polls would let the sections disagree with each other mid-scan, and a
    QR panel that says 未连接 next to a group list that says 已连接 is worse than
    a slower refresh.
    """

    checks: list[CheckOut] = Field(default_factory=list)
    problems: int = 0
    napcat: NapCatOut
    link: LinkOut
    sources: list[SourceOut] = Field(default_factory=list)
    scheduler_ready: bool = False
    extractor_ready: bool = False
    """An extraction model is configured, so L2 can actually run."""


class SetupActionOut(BaseModel):
    """Result of a button press on the 接入 page.

    Errors come back here with ``ok=False`` and a sentence a student can act on,
    not as a 500: the page is the only surface they have, so a failed install has
    to be readable in it.
    """

    ok: bool
    detail: str = ""
    napcat: NapCatOut | None = None


class NapCatLogOut(BaseModel):
    """NapCat's console, and the login QR pulled out of it.

    ``qrcode`` is the block-character drawing NapCat prints on stdout, sliced out
    of the log so the page can put it in a tight monospace box -- the surrounding
    log lines are long enough to force wrapping, and a wrapped QR does not scan.
    """

    log: str = ""
    qrcode: str = ""
    running: bool = False


class ReminderTestOut(BaseModel):
    """Result of a manual push.

    ``preview`` is returned whether or not delivery worked, so the student can
    see exactly what the reminder would say even with no platform attached.
    """

    delivered: bool
    preview: str
    detail: str = ""


__all__ = [
    "BACKUP_KIND",
    "BACKUP_VERSION",
    "BackupDocument",
    "BackupExtraction",
    "BackupOut",
    "BackupProfile",
    "BackupSetting",
    "BackupSource",
    "BackupTask",
    "TRANSFER_KIND",
    "TRANSFER_VERSION",
    "CheckOut",
    "CreateTaskIn",
    "DeleteSourceOut",
    "ExportOut",
    "ImportIn",
    "ImportOut",
    "LinkOut",
    "NotifyOut",
    "NotifyTargetOut",
    "NotifyTestOut",
    "UpdateNotifyIn",
    "NapCatLogOut",
    "NapCatOut",
    "ProfileOut",
    "ReminderOut",
    "SetupActionOut",
    "SetupStatusOut",
    "ReminderTestOut",
    "RestoreIn",
    "RestoreOut",
    "SourceOut",
    "StatsOut",
    "TaskDetailOut",
    "TaskOut",
    "TaskTransfer",
    "TraceOut",
    "TraceStep",
    "UpdateProfileIn",
    "UpdateSourceIn",
    "UpdateTaskIn",
    "short_umo",
]
