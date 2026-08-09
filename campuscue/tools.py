"""The agent's hands: what a student can ask CampusCue to do.

The extraction pipeline is the silent half of the product -- it reads the group
and files tasks without being asked. These five tools are the half the student
drives: "我还有什么没交", "实验三我交了", "这个比赛我要不要参加".

Conventions, following astrbot's own builtin tools (astrbot/core/tools/cron_tools.py)
-----------------------------------------------------------------------------------
Return values are plain strings, and failures start with ``error:``. The string
goes back into the model's context to be paraphrased, so it reads as a sentence;
returning JSON here would get field names transcribed into the reply.

Times are rendered in campus time and accepted as absolute ISO datetimes. The
model is never asked to do date arithmetic -- the same division of labour as the
extraction pipeline, where the model copies a time phrase and code resolves it --
so ``list_tasks`` also hands back a pre-computed "还剩 3 天" phrase rather than
leaving a subtraction to a component that cannot be trusted with one.

Scope: every tool reads ``event.unified_msg_origin``, so a call made in one group
can only see and touch that group's tasks.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from campuscue import reminders, store
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import TASK_TYPES, CampusTask, as_utc

MAX_LISTED = 20
"""Cap on tasks handed to the model at once. A long list crowds the conversation
out of the context window, and a student with sixty open items does not need all
sixty read back to them."""

MAX_LEAD_MINUTES = 60 * 24 * 90
"""Ninety days. Anything larger is a unit mistake by the model, not a request."""


# --- shared helpers --------------------------------------------------------


def _umo(context: ContextWrapper[AstrAgentContext]) -> str:
    return context.context.event.unified_msg_origin


def _fmt(moment: datetime | None) -> str:
    """A deadline, in the student's own timezone.

    Everything is stored UTC (see campuscue/models.py:as_utc); rendering without
    the conversion is how the 8-hour bug would reappear here.
    """
    local = as_utc(moment)
    if local is None:
        return "无截止时间"
    return local.astimezone(CAMPUS_TZ).strftime("%Y-%m-%d %H:%M")


def _remaining(deadline: datetime | None, now: datetime) -> str:
    """How long is left, as a phrase.

    Computed here rather than left to the model: a model that gets this
    subtraction wrong produces a confidently false reassurance, which is worse
    than not answering at all.
    """
    resolved = as_utc(deadline)
    if resolved is None:
        return "无截止"
    seconds = (resolved - now).total_seconds()
    if seconds < 0:
        overdue = -seconds
        if overdue < 3600:
            return f"已逾期 {int(overdue // 60)} 分钟"
        if overdue < 86400:
            return f"已逾期 {int(overdue // 3600)} 小时"
        return f"已逾期 {int(overdue // 86400)} 天"
    if seconds < 3600:
        return f"还剩 {int(seconds // 60)} 分钟"
    if seconds < 86400:
        return f"还剩 {int(seconds // 3600)} 小时"
    return f"还剩 {int(seconds // 86400)} 天"


def _parse_when(raw: object) -> datetime | None:
    """Parse an absolute ISO datetime from a tool argument.

    A value with no offset is read as campus time: when the model echoes back a
    time the student said out loud, they meant the clock on their own wall.
    """
    if raw in (None, ""):
        return None
    text = str(raw).strip().replace("/", "-")
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CAMPUS_TZ)
    return parsed.astimezone(timezone.utc)


def _line(task: CampusTask, now: datetime) -> str:
    """One task on one line, with everything the model needs to talk about it."""
    bits = [
        f"[{task.task_id[:8]}]",
        task.title,
        f"({task.task_type})",
        f"截止 {_fmt(task.deadline)}",
        _remaining(task.deadline, now),
    ]
    if task.deadline is not None and not task.deadline_is_explicit:
        bits.append("时间为推断")
    if task.location:
        bits.append(f"地点 {task.location}")
    if task.items:
        bits.append("需带 " + "、".join(str(i) for i in task.items))
    if task.status == "pending_confirm":
        bits.append("待确认")
    if task.reminder_job_ids:
        bits.append(f"已排 {len(task.reminder_job_ids)} 个提醒")
    return " | ".join(bits)


async def _resolve(umo: str, handle: str) -> CampusTask | None:
    """Find a task by full id, id prefix, or exact title.

    Prefixes are accepted because listings show a truncated id to keep lines
    readable, and the model hands back what it was shown. An ambiguous handle
    resolves to nothing rather than to a guess: silently completing the wrong
    task is worse than asking the student again.
    """
    handle = (handle or "").strip()
    if not handle:
        return None

    direct = await store.get_task(handle)
    if direct is not None and direct.umo == umo:
        return direct

    candidates = await store.list_tasks(
        umo,
        statuses=("active", "pending_confirm", "done", "dismissed"),
        limit=500,
    )
    by_prefix = [t for t in candidates if t.task_id.startswith(handle)]
    if len(by_prefix) == 1:
        return by_prefix[0]
    by_title = [t for t in candidates if t.title == handle]
    if len(by_title) == 1:
        return by_title[0]
    return None


async def _reschedule(task: CampusTask, leads: list[int] | None = None) -> list:
    """Reschedule reminders, swallowing failures.

    A tool that reports success and then raises on the scheduling step leaves the
    student believing their task was lost. The task is the product; the alarm is
    best-effort, so a failure is logged rather than surfaced as a tool error.
    """
    try:
        return await reminders.schedule_for_task(task, lead_override=leads)
    except Exception:  # noqa: BLE001
        logger.exception("[campuscue] tool could not schedule %s", task.task_id)
        return []


async def _publish(task_id: str, event: str) -> None:
    """Nudge any open board, so a tool call shows up without a refresh."""
    try:
        from campuscue.api.events import hub
        from campuscue.api.schemas import TaskOut

        fresh = await store.get_task(task_id)
        if fresh is not None:
            hub.publish(event, TaskOut.of(fresh).model_dump(mode="json"))
    except Exception:  # noqa: BLE001
        logger.debug("[campuscue] could not publish %s", event, exc_info=True)


# --- 1. create -------------------------------------------------------------


@dataclass
class CampusCreateTaskTool(FunctionTool[AstrAgentContext]):
    name: str = "campus_create_task"
    description: str = (
        "Create a campus task (homework, exam, competition, activity, notice) and "
        "schedule its reminders. Use when the student asks you to remember or add "
        "something. The deadline must be an absolute ISO datetime -- work out any "
        "relative wording against the current time before calling."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short title, e.g. 提交软件工程实验三报告.",
                },
                "task_type": {
                    "type": "string",
                    "enum": list(TASK_TYPES),
                    "description": "Kind of affair. Decides how early reminders fire.",
                },
                "deadline": {
                    "type": "string",
                    "description": "Absolute ISO datetime, e.g. 2026-08-14T23:59:00+08:00. Omit only if genuinely undated.",
                },
                "location": {"type": "string", "description": "Where, if relevant."},
                "items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Things to bring, e.g. ['身份证','校园卡'].",
                },
                "detail": {"type": "string", "description": "Extra notes."},
            },
            "required": ["title"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        title = str(kwargs.get("title") or "").strip()
        if not title:
            return "error: title is required."

        task_type = str(kwargs.get("task_type") or "notice").strip()
        if task_type not in TASK_TYPES:
            task_type = "notice"

        try:
            deadline = _parse_when(kwargs.get("deadline"))
        except (TypeError, ValueError):
            return (
                "error: deadline must be an absolute ISO datetime, "
                "e.g. 2026-08-14T23:59:00+08:00."
            )

        umo = _umo(context)
        now = datetime.now(timezone.utc)
        items = [str(i) for i in (kwargs.get("items") or []) if str(i).strip()]
        key = store.dedup_key(umo, title, deadline)

        # The student dictating something the pipeline already extracted is
        # common ("帮我记一下老师刚发的作业"), and creating it twice would produce two
        # sets of reminders for one obligation.
        async with store.db_helper.get_db() as session:
            existing = await store.find_duplicate(session, umo=umo, key=key, now=now)
        if existing is not None:
            return f"该任务已存在，未重复创建：{_line(existing, now)}"

        task = await store.create_task(
            CampusTask(
                umo=umo,
                title=title,
                task_type=task_type,
                status="active",
                deadline=deadline,
                deadline_is_explicit=deadline is not None,
                location=str(kwargs.get("location") or "").strip() or None,
                items=items,
                detail=str(kwargs.get("detail") or "").strip() or None,
                confidence=1.0,
                # A human asserted this one. The board shows the distinction, and
                # the demo can prove which path produced which task.
                source_kind="manual",
                dedup_key=key,
            )
        )

        planned = await _reschedule(task)
        note = (
            "已排提醒：" + "、".join(p.label for p in planned)
            if planned
            else "未排提醒（无截止时间或可提醒时间已过）"
        )
        await _publish(task.task_id, "task_created")
        return f"已创建：{_line(task, now)}\n{note}"


# --- 2. list ---------------------------------------------------------------


@dataclass
class CampusListTasksTool(FunctionTool[AstrAgentContext]):
    name: str = "campus_list_tasks"
    description: str = (
        "List the student's campus tasks with deadlines and time remaining. Use "
        "for any question about what is due, what is left, or what is overdue. "
        "The returned times and remaining phrases are already correct -- repeat "
        "them, do not recompute them."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["open", "today", "week", "overdue", "done", "pending"],
                    "description": "open = everything outstanding (default). pending = only those awaiting the student's confirmation.",
                },
                "task_type": {
                    "type": "string",
                    "enum": list(TASK_TYPES),
                    "description": "Optional filter by kind.",
                },
            },
            "required": [],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        umo = _umo(context)
        scope = str(kwargs.get("scope") or "open").strip()
        now = datetime.now(timezone.utc)

        statuses = {
            "pending": ("pending_confirm",),
            "done": ("done",),
        }.get(scope, ("active", "pending_confirm"))

        tasks = await store.list_tasks(umo, statuses=statuses, limit=200)

        wanted_type = str(kwargs.get("task_type") or "").strip()
        if wanted_type in TASK_TYPES:
            tasks = [t for t in tasks if t.task_type == wanted_type]

        if scope in ("today", "week"):
            end = (
                now.astimezone(CAMPUS_TZ)
                .replace(hour=23, minute=59, second=59)
                .astimezone(timezone.utc)
                if scope == "today"
                else now + timedelta(days=7)
            )
            tasks = [t for t in tasks if _within(t, now, end)]
        elif scope == "overdue":
            tasks = [t for t in tasks if _is_overdue(t, now)]

        if not tasks:
            return {
                "today": "今天没有到期的任务。",
                "week": "未来一周没有到期的任务。",
                "overdue": "没有逾期任务。",
                "pending": "没有待确认的任务。",
                "done": "还没有已完成的任务。",
            }.get(scope, "当前没有待办任务。")

        shown = tasks[:MAX_LISTED]
        header = f"共 {len(tasks)} 条"
        if len(tasks) > len(shown):
            header += f"，按截止时间显示最近 {len(shown)} 条"
        return header + "：\n" + "\n".join(_line(t, now) for t in shown)


def _within(task: CampusTask, start: datetime, end: datetime) -> bool:
    resolved = as_utc(task.deadline)
    return resolved is not None and start <= resolved <= end


def _is_overdue(task: CampusTask, now: datetime) -> bool:
    resolved = as_utc(task.deadline)
    return resolved is not None and resolved < now


# --- 3. complete -----------------------------------------------------------


@dataclass
class CampusCompleteTaskTool(FunctionTool[AstrAgentContext]):
    name: str = "campus_complete_task"
    description: str = (
        "Mark a campus task done, dismiss one that was never real, or reopen one. "
        "Cancels or rebuilds its reminders accordingly. Identify the task by the "
        "id shown in campus_list_tasks, or by its exact title."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task id (full, or the short prefix shown in a listing) or exact title.",
                },
                "action": {
                    "type": "string",
                    "enum": ["done", "dismiss", "reopen"],
                    "description": "done = finished it. dismiss = it was not a real task. reopen = undo either.",
                },
            },
            "required": ["task"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        umo = _umo(context)
        handle = str(kwargs.get("task") or "")
        task = await _resolve(umo, handle)
        if task is None:
            return (
                f"error: 找不到 “{handle.strip()}”，或有多条同名任务。"
                "先用 campus_list_tasks 拿到 id 再试。"
            )

        action = str(kwargs.get("action") or "done").strip()
        status = {"done": "done", "dismiss": "dismissed", "reopen": "active"}.get(
            action, "done"
        )
        label = {"done": "已完成", "dismissed": "已忽略", "active": "进行中"}[status]
        if task.status == status:
            return f"{task.title} 已经是{label}状态，无需重复操作。"

        updated = await store.update_task(task.task_id, status=status)
        if updated is None:
            return "error: 任务更新失败。"

        # done/dismissed cancels without rescheduling; reopen re-derives from the
        # deadline. schedule_for_task decides which, from the status.
        planned = await _reschedule(updated)
        await _publish(updated.task_id, "task_updated")

        if status == "active":
            tail = (
                f"，重新排了 {len(planned)} 个提醒" if planned else "，没有可排的提醒"
            )
            return f"已恢复：{updated.title}{tail}。"
        return f"{label}：{updated.title}，已取消其提醒。"


# --- 4. set_reminder -------------------------------------------------------


@dataclass
class CampusSetReminderTool(FunctionTool[AstrAgentContext]):
    name: str = "campus_set_reminder"
    description: str = (
        "Change when a task's reminders fire, or correct its deadline. Use when "
        "the student says a deadline moved, or asks to be reminded earlier or "
        "later. Reminders are created automatically otherwise, so this is for "
        "corrections rather than for every new task."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task id (full or short prefix) or exact title.",
                },
                "deadline": {
                    "type": "string",
                    "description": "New absolute ISO deadline, if it moved. Reminders are re-derived from it.",
                },
                "lead_minutes": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Minutes before the deadline to remind, e.g. [4320, 1440] for 3 days and 1 day ahead. The deadline itself is always included. Applies to this task only.",
                },
            },
            "required": ["task"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        umo = _umo(context)
        handle = str(kwargs.get("task") or "")
        task = await _resolve(umo, handle)
        if task is None:
            return f"error: 找不到 “{handle.strip()}”。先用 campus_list_tasks 拿到 id。"
        if task.status not in ("active", "pending_confirm"):
            return (
                f"error: {task.title} 已经是 {task.status} 状态，不再提醒。"
                "需要的话先用 campus_complete_task 的 reopen 恢复。"
            )

        if kwargs.get("deadline"):
            try:
                deadline = _parse_when(kwargs.get("deadline"))
            except (TypeError, ValueError):
                return (
                    "error: deadline must be an absolute ISO datetime, "
                    "e.g. 2026-08-14T23:59:00+08:00."
                )
            task = await store.update_task(
                task.task_id,
                deadline=deadline,
                # Hand-set by a human, so it is exact by definition.
                deadline_is_explicit=True,
                dedup_key=store.dedup_key(umo, task.title, deadline),
            )
            if task is None:
                return "error: 任务更新失败。"

        if task.deadline is None:
            return f"error: {task.title} 没有截止时间，要先设定截止时间才能排提醒。"

        raw_leads = kwargs.get("lead_minutes") or []
        leads = [
            int(m)
            for m in raw_leads
            if isinstance(m, (int, float)) and 0 <= int(m) <= MAX_LEAD_MINUTES
        ]
        if raw_leads and not leads:
            return f"error: lead_minutes 必须是 0 到 {MAX_LEAD_MINUTES} 之间的分钟数。"

        planned = await _reschedule(task, leads or None)
        if not planned:
            return (
                f"{task.title} 截止 {_fmt(task.deadline)}，"
                "按这个提前量算所有提醒时间都已经过了，没有排。"
            )

        detail = "、".join(
            f"{p.label}（{p.fire_at.astimezone(CAMPUS_TZ):%m-%d %H:%M}"
            + ("，避开免打扰" if p.shifted else "")
            + "）"
            for p in planned
        )
        await _publish(task.task_id, "task_updated")
        return f"{task.title} 截止 {_fmt(task.deadline)}，已排提醒：{detail}。"


# --- 5. analyze_opportunity ------------------------------------------------


@dataclass
class CampusAnalyzeOpportunityTool(FunctionTool[AstrAgentContext]):
    name: str = "campus_analyze_opportunity"
    description: str = (
        "Check whether the student realistically has room for a competition or "
        "activity, by reading what else is already due in the same window. "
        "Returns the actual conflicting tasks and computed load figures. Use them "
        "to advise -- do not invent a schedule."
    )
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "What the student is considering, e.g. 全国大学生数学建模竞赛.",
                },
                "deadline": {
                    "type": "string",
                    "description": "Absolute ISO datetime it is due or held.",
                },
                "effort_days": {
                    "type": "integer",
                    "description": "Rough days of work it would take. Defaults to 3.",
                },
            },
            "required": ["title", "deadline"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        title = str(kwargs.get("title") or "").strip()
        if not title:
            return "error: title is required."
        try:
            deadline = _parse_when(kwargs.get("deadline"))
        except (TypeError, ValueError):
            return "error: deadline must be an absolute ISO datetime."
        if deadline is None:
            return "error: deadline is required to judge whether the time exists."

        raw_effort = kwargs.get("effort_days")
        effort_days = int(raw_effort) if isinstance(raw_effort, (int, float)) else 3
        effort_days = max(1, min(effort_days, 60))

        now = datetime.now(timezone.utc)
        if deadline <= now:
            return f"error: {title} 的时间 {_fmt(deadline)} 已经过了。"

        umo = _umo(context)
        # The work window: the last ``effort_days`` before the deadline, clipped
        # to start no earlier than now. Anything due inside it competes for the
        # same hours. This is the student's real schedule read out of the
        # database -- the whole point of the tool is that the model does not get
        # to guess what they are busy with.
        window_start = max(now, deadline - timedelta(days=effort_days))
        conflicts = await store.count_open_tasks_between(umo, window_start, deadline)
        available_days = (deadline - now).total_seconds() / 86400

        lines = [
            f"机会：{title}",
            f"时间：{_fmt(deadline)}（{_remaining(deadline, now)}）",
            f"预计投入 {effort_days} 天，到截止还有 {available_days:.1f} 天",
        ]
        if available_days < effort_days:
            lines.append(
                f"⚠ 时间不足：可用 {available_days:.1f} 天 < 需要 {effort_days} 天"
            )

        if conflicts:
            lines.append(f"冲突：备赛窗口内还有 {len(conflicts)} 件事要交")
            lines.extend(f"  · {_line(t, now)}" for t in conflicts[:8])
            if len(conflicts) > 8:
                lines.append(f"  · 另有 {len(conflicts) - 8} 条")
        else:
            lines.append("冲突：备赛窗口内没有其它到期任务")

        exams = [t for t in conflicts if t.task_type == "exam"]
        if exams:
            lines.append(
                f"⚠ 窗口内有 {len(exams)} 场考试："
                + "、".join(t.title for t in exams[:3])
            )

        # A load figure, not a verdict. The tool supplies numbers and the real
        # list; the model does the advising, because only it knows what the
        # student said they cared about. Hard-coding "建议参加" here would make a
        # database query pretend to be judgement.
        load = len(conflicts) / max(available_days, 0.5)
        lines.append(f"负载：窗口内 {load:.1f} 件/天")
        return "\n".join(lines)


# --- registration ----------------------------------------------------------

ALL_TOOLS: tuple[type[FunctionTool], ...] = (
    CampusCreateTaskTool,
    CampusListTasksTool,
    CampusCompleteTaskTool,
    CampusSetReminderTool,
    CampusAnalyzeOpportunityTool,
)


def build_tools() -> list[FunctionTool]:
    """Instantiate the campus toolset.

    Registered through ``Context.add_llm_tools`` from the star rather than with
    ``@builtin_tool``: the registry's module list lives in
    astrbot/core/tools/registry.py, and adding to it would be a fourth edit
    inside ``astrbot/`` for no gain over the documented plugin path.
    """
    return [cls() for cls in ALL_TOOLS]


__all__ = [
    "ALL_TOOLS",
    "CampusAnalyzeOpportunityTool",
    "CampusCompleteTaskTool",
    "CampusCreateTaskTool",
    "CampusListTasksTool",
    "CampusSetReminderTool",
    "build_tools",
]
