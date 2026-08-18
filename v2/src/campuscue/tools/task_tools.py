"""Task Tools (M4 §17-23) — the first CampusCue tools, source-scoped.

SECURITY (M4 §14): every tool operates ONLY within the CURRENT source
conversation. A model hallucinating a foreign task id hits a safe Not Found
ToolResult — no cross-source existence leak. Scope comes from the trusted
ToolContext, never from model arguments (schemas reject scope fields).

MUTATION GATE (M4 §16): ALL mutations go through TaskService (create /
update_task / complete / dismiss) — the single business gate. Tools never
touch Repository or DB sessions directly. M3 reminder coupling (deadline
change -> plan rebuild; complete/dismiss -> cancel) is preserved inside
TaskService; tools create no second mutation pathway.

Privacy (M4 §54): tool content returns task facts to the model (inside the
conversation only) — NEVER logged; logs carry trace_id + tool name only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from campuscue.repositories.repositories import NotFoundError
from campuscue.services.reminder_service import ReminderService
from campuscue.services.task_service import DEADLINE_UNSET, TaskService
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import ReminderStatus, TaskCategory, TaskStatus
from campuscue.storage.models import Task
from campuscue.tasks.dedup import build_dedup_key
from campuscue.tasks.models import TaskCandidate
from campuscue.tasks.time_normalizer import resolve_deadline
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import ToolDefinition, ToolResult

_SCOPE_VALUES = ["open", "today", "week", "overdue", "done", "pending"]
_REMINDER_STATUS_VALUES = [s.value for s in ReminderStatus]
_CATEGORY_VALUES = [c.value for c in TaskCategory]

_UNFINISHED = {TaskStatus.PENDING.value, TaskStatus.PENDING_CONFIRM.value}


def _require_source(context: ToolContext) -> int | ToolResult:
    if context.source_id is None:
        return ToolResult(
            ok=False, content="", error="当前会话未接入任务数据，无法使用任务工具"
        )
    return context.source_id


def _fmt_dt(dt: datetime | None, tz: ZoneInfo) -> str:
    if dt is None:
        return "无截止"
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M")


def _remain_text(deadline: datetime, now: datetime) -> str:
    delta = deadline - now
    if delta.total_seconds() < 0:
        return "已过期"
    days = int(delta.total_seconds() // 86400)
    if days == 0:
        return "今天截止"
    return f"剩{days}天"


def _task_summary(task: Task, now: datetime, tz: ZoneInfo) -> str:
    """Compact structured line for the model (no ORM repr, no secrets)."""
    course = f"{task.course}·" if task.course else ""
    rest = ""
    if task.deadline is not None:
        rest = f" | 截止 {_fmt_dt(task.deadline, tz)}（{_remain_text(task.deadline, now)}）"
    return f"#{task.id} {course}{task.title} | {task.status}{rest}"


def _resolve_phrase(phrase: str | None, *, context: ToolContext) -> tuple[datetime | None, str | None]:
    """Deterministic CampusCue time normalization (M4 §20): never trust an
    arbitrary naive datetime from the model. Returns (aware UTC deadline,
    error) — error when the phrase cannot be resolved (ask for clarification,
    never invent a date)."""
    if not phrase or not phrase.strip():
        return None, None
    resolved = resolve_deadline(phrase, context.timestamp, context.timezone)
    if resolved.deadline is None:
        return None, f"无法解析截止时间“{phrase}”，请换一种说法（如“周五晚上12点前”或“8月20日”）"
    return resolved.deadline, None


class TaskListTool(ToolDefinition):
    name = "task_list"
    description = (
        "查询当前会话的任务列表。scope 取值：open（未完成，默认）、pending（已接受）、"
        "today（今天截止）、week（未来7天）、overdue（已过期）、done（已完成）"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "scope": {"type": "string", "enum": _SCOPE_VALUES, "default": "open"},
        },
        "additionalProperties": False,
    }

    def __init__(
        self, task_service: TaskService, *, clock: Clock | None = None, tz: ZoneInfo
    ) -> None:
        self._tasks = task_service
        self._clock = clock or SystemClock()
        self._tz = tz

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        scope = kwargs.get("scope") or "open"
        now = self._clock.utcnow()
        try:
            tasks = await self._tasks.list_for_source(
                sid, scope=scope, now=now, tz=self._tz
            )
        except ValueError as e:
            return ToolResult(ok=False, content="", error=str(e))
        if not tasks:
            return ToolResult(ok=True, content="当前会话没有任务。", data={"count": 0})
        lines = [
            f"当前会话任务（{scope}）共 {len(tasks)} 个：",
            *[f"- {_task_summary(t, now, self._tz)}" for t in tasks],
        ]
        return ToolResult(
            ok=True,
            content="\n".join(lines),
            data={"count": len(tasks), "scope": scope},
        )


class TaskGetTool(ToolDefinition):
    name = "task_get"
    description = "查看单个任务的详细信息（需提供任务 ID）"
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "integer", "minimum": 1}},
        "required": ["task_id"],
        "additionalProperties": False,
    }

    def __init__(self, task_service: TaskService, *, clock: Clock | None = None, tz: ZoneInfo) -> None:
        self._tasks = task_service
        self._clock = clock or SystemClock()
        self._tz = tz

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        task_id = int(kwargs["task_id"])
        try:
            task = await self._tasks.get_for_source(sid, task_id)
        except NotFoundError:
            return ToolResult(
                ok=False, content="", error="task_not_found",
                data={"task_id": task_id},
            )
        now = self._clock.utcnow()
        lines = [
            f"任务 #{task.id}：",
            f"- 标题：{task.title}",
            f"- 分类：{task.category}",
            f"- 课程：{task.course or '（未设置）'}",
            f"- 截止：{_fmt_dt(task.deadline, self._tz)}"
            + (f"（{_remain_text(task.deadline, now)}）" if task.deadline else ""),
            f"- 状态：{task.status}",
            f"- 优先级：{task.priority}",
        ]
        if task.source_text_reference:
            # same-source task content is in-conversation; NEVER logged (M4 §19)
            lines.append(f"- 来源：{task.source_text_reference[:200]}")
        return ToolResult(ok=True, content="\n".join(lines), data={"task_id": task.id})


class TaskCreateTool(ToolDefinition):
    name = "task_create"
    description = (
        "用户口述创建任务（当前会话）。title 必填；category 取值：homework（作业）/exam（考试）"
        "/competition（比赛）/activity（活动）/notice（通知）/other（其他）；"
        "deadline_phrase 用自然语言描述截止时间，如“周五晚上12点前”“8月20日”。"
        "同一条用户消息最多只能创建一个任务；第二次调用会失败，请如实告知用户"
    )
    # M4 first-version limitation: M2 UNIQUE(source_id, source_message_id) means
    # one Agent user message can create at most one Task. A second task_create in
    # the same turn returns a safe failure (never falsely created). No schema v3.
    input_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "category": {"type": "string", "enum": _CATEGORY_VALUES, "default": "other"},
            "course": {"type": "string"},
            "deadline_phrase": {"type": "string"},
        },
        "required": ["title"],
        "additionalProperties": False,
    }

    def __init__(self, task_service: TaskService, *, tz: ZoneInfo) -> None:
        self._tasks = task_service
        self._tz = tz

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        title = str(kwargs["title"]).strip()
        if not title:
            return ToolResult(ok=False, content="", error="任务标题不能为空")
        deadline, err = _resolve_phrase(kwargs.get("deadline_phrase"), context=context)
        if err is not None:
            return ToolResult(ok=False, content="", error=err)
        candidate = TaskCandidate(
            title=title,
            category=kwargs.get("category") or TaskCategory.OTHER.value,
            course=kwargs.get("course") or None,
            deadline=deadline,
            description=None,
            confidence=1.0,
            dedup_key=build_dedup_key(
                title=title,
                course=kwargs.get("course") or None,
                deadline=deadline,
            ),
            source_id=sid,
            # trusted values from runtime context — the model cannot control them
            source_message_id=context.message_id,
            source_text_reference=context.user_text,
            pending_confirm=False,
        )
        result = await self._tasks.create_task(candidate)
        if not result.created:
            return ToolResult(
                ok=False,
                content=f"任务未创建（重复：{result.reason}），请勿重复添加。",
                data={"created": False, "reason": result.reason},
            )
        task = result.task
        assert task is not None
        return ToolResult(
            ok=True,
            content=f"已创建任务 #{task.id}：{task.title}"
            + (f"，截止 {_fmt_dt(task.deadline, self._tz)}" if task.deadline else ""),
            data={"created": True, "task_id": task.id},
        )


class TaskUpdateTool(ToolDefinition):
    name = "task_update"
    description = (
        "更新任务（当前会话，仅 pending 状态可改）。可改字段：title、course、deadline_phrase"
        "（自然语言截止时间）。至少提供一个字段"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {"type": "integer", "minimum": 1},
            "title": {"type": "string", "minLength": 1, "maxLength": 200},
            "course": {"type": "string"},
            "deadline_phrase": {"type": "string"},
        },
        "required": ["task_id"],
        "additionalProperties": False,
    }

    def __init__(self, task_service: TaskService, *, tz: ZoneInfo) -> None:
        self._tasks = task_service
        self._tz = tz

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        task_id = int(kwargs["task_id"])
        deadline = None
        if "deadline_phrase" in kwargs:
            resolved, err = _resolve_phrase(kwargs["deadline_phrase"], context=context)
            if err is not None:
                return ToolResult(ok=False, content="", error=err)
            deadline = resolved
        try:
            task = await self._tasks.update_task(
                sid,
                task_id,
                title=kwargs.get("title"),
                course=kwargs.get("course"),
                # DEADLINE_UNSET = deadline not provided -> leave unchanged
                deadline=deadline if "deadline_phrase" in kwargs else DEADLINE_UNSET,
            )
        except NotFoundError:
            return ToolResult(ok=False, content="", error="task_not_found", data={"task_id": task_id})
        except ValueError as e:
            return ToolResult(ok=False, content="", error=str(e), data={"task_id": task_id})
        return ToolResult(
            ok=True,
            content=f"已更新任务 #{task.id}：{task.title}"
            + (f"，截止 {_fmt_dt(task.deadline, self._tz)}" if task.deadline else ""),
            data={"task_id": task.id},
        )


class TaskCompleteTool(ToolDefinition):
    name = "task_complete"
    description = "将任务标记为已完成（当前会话；会取消该任务的提醒）"
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "integer", "minimum": 1}},
        "required": ["task_id"],
        "additionalProperties": False,
    }

    def __init__(self, task_service: TaskService) -> None:
        self._tasks = task_service

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        task_id = int(kwargs["task_id"])
        try:
            task = await self._tasks.get_for_source(sid, task_id)
            if task.status == TaskStatus.DONE.value:
                return ToolResult(
                    ok=False, content=f"任务 #{task_id} 已完成，无需重复操作。",
                    data={"task_id": task_id},
                )
            task = await self._tasks.complete(task_id)
        except NotFoundError:
            return ToolResult(ok=False, content="", error="task_not_found", data={"task_id": task_id})
        return ToolResult(
            ok=True, content=f"任务 #{task.id} 已标记完成。", data={"task_id": task.id}
        )


class TaskDismissTool(ToolDefinition):
    name = "task_dismiss"
    description = "忽略/放弃一个任务（当前会话；会取消该任务的提醒）"
    input_schema = {
        "type": "object",
        "properties": {"task_id": {"type": "integer", "minimum": 1}},
        "required": ["task_id"],
        "additionalProperties": False,
    }

    def __init__(self, task_service: TaskService) -> None:
        self._tasks = task_service

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        task_id = int(kwargs["task_id"])
        try:
            task = await self._tasks.get_for_source(sid, task_id)
            if task.status == TaskStatus.DISMISSED.value:
                return ToolResult(
                    ok=False, content=f"任务 #{task_id} 已忽略，无需重复操作。",
                    data={"task_id": task_id},
                )
            task = await self._tasks.dismiss(task_id)
        except NotFoundError:
            return ToolResult(ok=False, content="", error="task_not_found", data={"task_id": task_id})
        return ToolResult(
            ok=True, content=f"任务 #{task.id} 已忽略。", data={"task_id": task.id}
        )


class ReminderListTool(ToolDefinition):
    name = "reminder_list"
    description = "查询当前会话任务的提醒安排（trigger 时间、类型、状态）"
    input_schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": _REMINDER_STATUS_VALUES, "default": "scheduled"},
        },
        "additionalProperties": False,
    }

    def __init__(
        self,
        reminder_service: ReminderService,
        task_service: TaskService,
        *,
        tz: ZoneInfo,
    ) -> None:
        self._reminders = reminder_service
        self._tasks = task_service
        self._tz = tz

    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        sid = _require_source(context)
        if isinstance(sid, ToolResult):
            return sid
        status = kwargs.get("status") or ReminderStatus.SCHEDULED.value
        rows = await self._reminders.list_for_source(sid)  # source-scoped query
        wanted = [r for r in rows if r.status == status]
        if not wanted:
            return ToolResult(ok=True, content="当前会话没有相关提醒。", data={"count": 0})
        lines = [f"当前会话提醒（{status}）共 {len(wanted)} 条："]
        for r in wanted:
            lines.append(
                f"- 任务#{r.task_id} | {r.type} | {r.trigger_at.astimezone(self._tz).strftime('%Y-%m-%d %H:%M')} | {r.status}"
            )
        return ToolResult(
            ok=True, content="\n".join(lines), data={"count": len(wanted), "status": status}
        )


def register_task_tools(
    registry,
    *,
    task_service: TaskService,
    reminder_service: ReminderService | None,
    tz: ZoneInfo,
    clock: Clock | None = None,
) -> None:
    """Register the canonical M4 task tool set (M4 §17). Tools are small;
    source_list is intentionally NOT added (no clear M4 use)."""
    clock = clock or SystemClock()
    registry.register(TaskListTool(task_service, clock=clock, tz=tz))
    registry.register(TaskGetTool(task_service, clock=clock, tz=tz))
    registry.register(TaskCreateTool(task_service, tz=tz))
    registry.register(TaskUpdateTool(task_service, tz=tz))
    registry.register(TaskCompleteTool(task_service))
    registry.register(TaskDismissTool(task_service))
    if reminder_service is not None:
        registry.register(
            ReminderListTool(reminder_service, task_service, tz=tz)
        )
