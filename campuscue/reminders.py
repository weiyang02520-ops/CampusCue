"""Scheduling: the half that makes CampusCue proactive rather than a todo list.

Extraction turns a group message into a dated task. This module is what makes
that matter -- without it the product is an auto-filled list the student still
has to remember to open.

Three design decisions worth reading before changing anything here.

1. Why basic jobs, not active_agent jobs
----------------------------------------
AstrBot's proactive channel is ``add_active_job``, which on fire builds the main
agent and runs ``step_until_done(30)`` so an LLM decides what to say
(astrbot/core/cron/manager.py:335). That is the right shape for "wake up and go
do something", and the wrong shape for a reminder: the text is already known, the
student is waiting on a deadline not a conversation, and it would put an LLM
round-trip, a configured default chat provider, and a 30-step agent loop between
the alarm and the notification. A reminder that says nothing because the provider
was misconfigured is worse than no reminder.

So reminders go out as ``add_basic_job`` + a fixed handler that pushes a
composed MessageChain through ``Context.send_message``. Deterministic text, no
tokens, no provider dependency, and still on the framework's scheduler and
visible in its cron WebUI. ``analyze_opportunity`` is where the LLM belongs.

2. Why the cron table is a cache, not the source of truth
---------------------------------------------------------
Every reminder is derivable from ``campus_tasks.deadline`` plus the student's
profile, so the schedule is rebuilt from the tasks on each boot
(``resync_all``) instead of being restored from ``cron_jobs``. This means the two
can never disagree: no orphan job firing for a task that was completed while the
process was down, no task silently missing its reminder because a job row was
lost. Jobs are therefore registered ``persistent=False`` -- AstrBot's
``sync_from_db`` skips them on startup, which is exactly what we want.

3. Why a pinned crontab expression instead of run_at
----------------------------------------------------
``add_active_job`` takes ``run_once``/``run_at``; ``add_basic_job`` does not.
Rather than patch the framework, a one-shot fire is expressed as a crontab
pinned to the minute, hour, day and month ("29 15 31 7 *"). Such an expression
would recur annually, so the handler deletes its own job as its final act -- and
because jobs are non-persistent, one that never fires is inert after a restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Any

from astrbot.core import logger
from campuscue import store
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import CampusTask, as_utc

if TYPE_CHECKING:
    from astrbot.core.cron.manager import CronJobManager
    from astrbot.core.star.context import Context

JOB_NAME_PREFIX = "campuscue:remind"
"""Marks jobs this module owns, so a stray one can be identified in the cron
WebUI and so cleanup never touches a job the student created by hand."""

DEFAULT_LEADS: dict[str, list[int]] = {
    "homework": [1440, 120],
    "exam": [2880, 720],
    "competition": [4320, 1440],
    "activity": [1440],
    "notice": [1440],
}
"""Fallback when a profile has no entry for a type. Mirrors CampusProfile's
defaults; duplicated rather than imported so a profile row with a partial map
still gets sensible leads for the types it omits."""

MIN_LEAD_SECONDS = 60
"""A reminder closer than this to the moment it is scheduled is dropped: it would
arrive alongside the action that created it and read as an echo."""


# --- the runtime handle ----------------------------------------------------
# The pipeline and the HTTP layer both need to schedule reminders, and neither is
# given a star context. Rather than thread one through every call site, the star
# publishes the two objects it owns here at load time. Both are None until then,
# and every function below degrades to a no-op rather than raising -- extraction
# must keep working even if the scheduler failed to come up.
_cron: CronJobManager | None = None
_ctx: Context | None = None


def bind(cron_manager: CronJobManager | None, context: Context | None) -> None:
    """Publish the scheduler and push channel. Called once, by the star."""
    global _cron, _ctx
    _cron = cron_manager
    _ctx = context


def is_bound() -> bool:
    return _cron is not None and _ctx is not None


def push_context() -> Context | None:
    """The bound star context, or None before the star has loaded.

    Public because ``campuscue.notify`` pushes through the same channel: the star
    owns exactly one context and two modules reaching for it via a private name
    would be two things to fix the day it moves.
    """
    return _ctx


@dataclass(frozen=True)
class PlannedReminder:
    """One reminder, decided but not yet scheduled."""

    fire_at: datetime
    """UTC, timezone-aware."""
    lead_minutes: int
    """The nominal lead this came from, before any quiet-hours adjustment."""
    label: str
    """Human phrasing of the lead, e.g. "提前 1 天". Goes into the push text."""
    shifted: bool = False
    """True when quiet hours moved this away from ``deadline - lead``."""


def describe_lead(minutes: int) -> str:
    """Phrase a lead in the largest unit that stays exact."""
    if minutes % 1440 == 0:
        return f"提前 {minutes // 1440} 天"
    if minutes % 60 == 0:
        return f"提前 {minutes // 60} 小时"
    return f"提前 {minutes} 分钟"


def _parse_hhmm(value: Any, fallback: time) -> time:
    """Parse "23:00" from a JSON profile column, tolerantly.

    The column is user-editable JSON, so a bad value must not take down
    scheduling for every task the student has.
    """
    if isinstance(value, str) and ":" in value:
        hh, _, mm = value.partition(":")
        try:
            return time(int(hh), int(mm))
        except ValueError:
            pass
    return fallback


def _in_quiet_window(moment: time, start: time, end: time) -> bool:
    """Whether a wall-clock time falls inside the quiet window.

    The window normally wraps midnight (23:00 to 07:30), which is why this is not
    a plain ``start <= moment < end``.
    """
    if start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def _apply_quiet_hours(
    fire_at: datetime, deadline: datetime, quiet: dict | None
) -> tuple[datetime, bool]:
    """Move a reminder out of the student's quiet window.

    Returns the adjusted instant and whether it moved. The default is to slide
    forward to the end of the window -- a nudge at 07:30 is useful, one at 03:00
    wakes someone up for nothing. But sliding forward past the deadline turns the
    reminder into a notification of failure, so in that case it moves *back* to
    just before the window began instead: early is annoying, late is useless.
    """
    if not quiet:
        return fire_at, False

    start = _parse_hhmm(quiet.get("start"), time(23, 0))
    end = _parse_hhmm(quiet.get("end"), time(7, 30))
    local = fire_at.astimezone(CAMPUS_TZ)
    if not _in_quiet_window(local.timetz().replace(tzinfo=None), start, end):
        return fire_at, False

    # Forward, to the end of the window. When the window wraps midnight and we
    # are already past it, the end belongs to the next day.
    slid = local.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    if slid <= local:
        slid += timedelta(days=1)
    if slid.astimezone(timezone.utc) < deadline:
        return slid.astimezone(timezone.utc), True

    # Backward, to just before the window opened.
    earlier = local.replace(
        hour=start.hour, minute=start.minute, second=0, microsecond=0
    )
    if earlier >= local:
        earlier -= timedelta(days=1)
    return earlier.astimezone(timezone.utc), True


def plan_reminders(
    *,
    deadline: datetime | None,
    task_type: str,
    now: datetime,
    lead_minutes: dict | None = None,
    quiet_hours: dict | None = None,
) -> list[PlannedReminder]:
    """Decide when to remind, for one task. Pure -- no scheduler, no database.

    Everything interesting about reminder timing is here so it can be tested
    against a fixed clock instead of by waiting.

    Leads that already passed are dropped rather than fired immediately: a task
    extracted the evening before its deadline should get the 2-hour nudge, not a
    burst of three catch-up pushes for leads that are moot. The deadline itself
    always produces a reminder if it is still in the future, so a task added late
    is never silent.
    """
    if deadline is None:
        # Genuinely undated tasks exist ("下周交，时间待通知"). They stay on the
        # board and get a reminder as soon as someone fills the deadline in.
        return []

    deadline = as_utc(deadline) or deadline
    leads = (
        (lead_minutes or {}).get(task_type) or DEFAULT_LEADS.get(task_type) or [1440]
    )
    # 0 = at the deadline itself. Always included: a student who dismisses the
    # early nudge still deserves the last call.
    wanted = sorted(
        {int(m) for m in leads if isinstance(m, (int, float))} | {0}, reverse=True
    )

    planned: list[PlannedReminder] = []
    taken: set[datetime] = set()
    for lead in wanted:
        raw = deadline - timedelta(minutes=lead)
        if lead > 0:
            fire_at, shifted = _apply_quiet_hours(raw, deadline, quiet_hours)
        else:
            # The final call is never moved. Silencing it because the deadline
            # falls at 02:00 would mean the one reminder that cannot be replaced
            # by a later one is the one that never arrives.
            fire_at, shifted = raw, False

        fire_at = fire_at.replace(second=0, microsecond=0)
        if (fire_at - now).total_seconds() < MIN_LEAD_SECONDS:
            continue
        if fire_at in taken:
            # Quiet-hours shifting can collapse two leads onto the same minute.
            continue
        taken.add(fire_at)
        planned.append(
            PlannedReminder(
                fire_at=fire_at,
                lead_minutes=lead,
                label="截止时间到" if lead == 0 else describe_lead(lead),
                shifted=shifted,
            )
        )

    planned.sort(key=lambda p: p.fire_at)
    return planned


def _crontab_for(moment: datetime) -> str:
    """A five-field crontab pinned to one minute of one day.

    Interpreted in the campus timezone, which is passed alongside as the job's
    ``timezone`` so the expression is not read against the server's locale.
    """
    local = moment.astimezone(CAMPUS_TZ)
    return f"{local.minute} {local.hour} {local.day} {local.month} *"


def compose_message(task: CampusTask, label: str) -> str:
    """The push text.

    Written to be readable in a QQ notification preview, which truncates hard:
    the title comes second, right after a four-character urgency phrase, so the
    student can tell from the lock screen whether to open it. Provenance goes
    last -- it matters when the student doubts the task, and by then they have
    opened the message.
    """
    deadline = as_utc(task.deadline)
    lines = [f"⏰ 课讯提醒 · {label}", task.title]

    if deadline is not None:
        local = deadline.astimezone(CAMPUS_TZ)
        stamp = local.strftime("%m-%d %H:%M")
        if not task.deadline_is_explicit:
            stamp += "（时间为推断）"
        lines.append(f"截止 {stamp}")

    if task.location:
        lines.append(f"📍 {task.location}")
    items = list(task.items or [])
    if items:
        lines.append(f"🎒 需带：{'、'.join(str(i) for i in items)}")

    origin = " · ".join(
        part for part in (task.source_group_name, task.source_sender_name) if part
    )
    if origin:
        lines.append(f"来自 {origin}")
    return "\n".join(lines)


async def _fire(task_id: str = "", label: str = "", job_id: str = "") -> None:
    """Deliver one reminder. Registered as a basic cron handler.

    Re-reads the task rather than closing over it: between scheduling and firing
    the student may have completed it, dismissed it, or corrected its deadline,
    and pushing a reminder for a task that is already done is the fastest way to
    get a student to mute the bot.
    """
    task = await store.get_task(task_id)
    if task is None:
        logger.debug("[campuscue] reminder for missing task %s, skipped", task_id)
    elif task.status not in ("active", "pending_confirm"):
        logger.info(
            "[campuscue] reminder skipped, task %s is %s", task.task_id, task.status
        )
    elif _ctx is None:
        logger.warning(
            "[campuscue] no context bound, reminder for task %s lost", task.task_id
        )
    else:
        from astrbot.core.message.message_event_result import MessageChain

        text = compose_message(task, label or "提醒")
        # Never back into the source group -- see campuscue/notify.py. The task's
        # own origin is only the fallback for an install where no target has been
        # designated yet.
        from campuscue import notify

        target = await notify.resolve_target(task.umo)
        try:
            delivered = await _ctx.send_message(target, MessageChain().message(text))
        except Exception:  # noqa: BLE001 - a dead platform must not kill the job
            logger.exception(
                "[campuscue] reminder push failed for task %s", task.task_id
            )
            delivered = False

        if delivered:
            await store.update_task(task_id, reminded_at=datetime.now(timezone.utc))
        else:
            # No platform matched the origin -- normal when replaying a demo
            # session with no QQ account attached. The board still shows it.
            logger.info(
                "[campuscue] no platform available; reminder for task %s not pushed",
                task.task_id,
            )

        try:
            from campuscue.api.events import hub

            hub.publish(
                "reminder_fired",
                {"task_id": task_id, "label": label, "delivered": delivered},
            )
        except Exception:  # noqa: BLE001 - the board is a nicety
            logger.debug("[campuscue] could not publish reminder event", exc_info=True)

    # Self-delete: see the module docstring on pinned crontabs. Runs even when
    # the task was gone, so a stale job cannot survive its own firing.
    if job_id and _cron is not None:
        try:
            await _cron.delete_job(job_id)
        except Exception:  # noqa: BLE001
            # The crontab expression is pinned to "minute hour day month *", so
            # a job that survives its firing would fire again on the same date
            # next year. Disabling it is the second-best outcome -- the row
            # stays, but nothing will ever trigger it again.
            logger.exception("[campuscue] could not delete fired job %s", job_id)
            try:
                await _cron.db.update_cron_job(job_id, enabled=False)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "[campuscue] could not disable leftover job %s", job_id
                )
        else:
            # The cron row is gone, so the task's own reference to it must be
            # too -- otherwise the board keeps reporting "有提醒" and cancel
            # paths count a deletion that can never happen again.
            if task is not None:
                try:
                    remaining = [
                        j for j in (task.reminder_job_ids or []) if j != job_id
                    ]
                    await store.update_task(task.task_id, reminder_job_ids=remaining)
                except Exception:  # noqa: BLE001 - cosmetic, reconciled on resync
                    logger.debug(
                        "[campuscue] could not drop fired job id from %s",
                        task.task_id,
                    )


async def cancel_for_task(task: CampusTask) -> int:
    """Drop every scheduled reminder a task owns. Returns how many went.

    Called when a task is completed, dismissed, or has its deadline edited.
    Tolerant of jobs that no longer exist: the schedule is a cache and being out
    of date is expected, not exceptional.
    """
    job_ids = list(task.reminder_job_ids or [])
    if not job_ids:
        return 0

    removed = 0
    if _cron is not None:
        for job_id in job_ids:
            try:
                await _cron.delete_job(job_id)
                removed += 1
            except Exception:  # noqa: BLE001
                logger.debug("[campuscue] job %s already gone", job_id)
    await store.update_task(task.task_id, reminder_job_ids=[])
    return removed


async def schedule_for_task(
    task: CampusTask,
    *,
    now: datetime | None = None,
    lead_override: list[int] | None = None,
) -> list[PlannedReminder]:
    """Plan and register this task's reminders, replacing any it already had.

    Idempotent by construction -- existing jobs are cancelled first -- so it is
    safe to call after every edit without tracking what changed.

    ``lead_override`` replaces the profile's leads for this task only. It exists
    for "提醒我提前三天" -- a student asking about one competition is not asking to
    change how every future competition is handled, so the override is not
    written back to the profile.
    """
    now = now or datetime.now(timezone.utc)
    if task.reminder_job_ids:
        await cancel_for_task(task)

    if task.status not in ("active", "pending_confirm"):
        return []

    # The lead-time channel is now optional: detection-time push is the primary
    # one (campuscue/notify.py), and a student who finds a second buzz the day
    # before redundant can turn this off without losing the detection notice.
    from campuscue import notify

    if not (await notify.get_settings()).deadline_reminders:
        logger.debug(
            "[campuscue] deadline reminders off, task %s not scheduled", task.task_id
        )
        return []

    async with store.db_helper.get_db() as session:
        profile = await store.get_or_create_profile(session, task.umo)
        leads = dict(profile.lead_minutes or {})
        quiet = dict(profile.quiet_hours or {})

    if lead_override is not None:
        leads[task.task_type] = list(lead_override)

    planned = plan_reminders(
        deadline=task.deadline,
        task_type=task.task_type,
        now=now,
        lead_minutes=leads,
        quiet_hours=quiet,
    )
    if not planned:
        return []
    if _cron is None:
        logger.debug(
            "[campuscue] scheduler unbound, task %s not scheduled", task.task_id
        )
        return []

    job_ids: list[str] = []
    for item in planned:
        try:
            job = await _cron.add_basic_job(
                name=f"{JOB_NAME_PREFIX}:{task.task_id}:{item.lead_minutes}",
                cron_expression=_crontab_for(item.fire_at),
                handler=_fire,
                description=f"{task.title} · {item.label}",
                timezone=str(CAMPUS_TZ),
                # job_id is filled in below: the handler needs it to delete
                # itself, and it does not exist until the row is created.
                payload={"task_id": task.task_id, "label": item.label},
                persistent=False,
            )
        except Exception:  # noqa: BLE001 - one bad lead must not lose the rest
            logger.exception("[campuscue] failed to schedule task %s", task.task_id)
            continue
        try:
            await _cron.db.update_cron_job(
                job.job_id,
                payload={
                    "task_id": task.task_id,
                    "label": item.label,
                    "job_id": job.job_id,
                },
            )
        except Exception:  # noqa: BLE001
            # The job is already registered and scheduled. Leaving it with no
            # job_id in the payload would make _fire unable to delete itself,
            # and the crontab expression (minute hour day month *) would fire
            # again on the same date next year -- so roll the row back instead
            # of silently keeping it.
            logger.exception("[campuscue] could not persist payload for %s", job.job_id)
            try:
                await _cron.delete_job(job.job_id)
            except Exception:  # noqa: BLE001
                logger.debug("[campuscue] could not roll back job %s", job.job_id)
            continue
        job_ids.append(job.job_id)

    if job_ids:
        await store.update_task(task.task_id, reminder_job_ids=job_ids)
    logger.info(
        "[campuscue] %d reminder(s) scheduled for task %s",
        len(job_ids),
        task.task_id,
    )
    return planned


async def resync_all(umo: str | None = None) -> dict[str, int]:
    """Rebuild the schedule from the tasks. Run once at startup.

    See the module docstring: the cron table is a cache. Anything that happened
    while the process was down -- a deadline edited through the API, a task
    completed, the clock crossing a lead -- is reconciled here by throwing the
    old schedule away and re-deriving it.

    With ``umo`` the reconcile is scoped to that origin. That scoping has to cover
    the sweep as well as the rebuild, and originally did not: a preference saved
    for one group deleted every ``campuscue:remind`` row in the table and then
    rebuilt only that group's, silently disarming every other group until the next
    restart. The job name carries its task id, which is what makes the narrow
    sweep possible.
    """
    if _cron is None:
        return {"tasks": 0, "reminders": 0, "cleared": 0}

    umos = [umo] if umo else await _known_umos()
    now = datetime.now(timezone.utc)
    scoped: list[CampusTask] = []
    for one in umos:
        scoped += await store.list_tasks(one, statuses=("active", "pending_confirm"))
    # Also sweep tasks that have since left the active set: a task completed while
    # the process was down still owns rows nothing else will ever clean up.
    owned = {t.task_id for t in scoped}
    if umo is not None:
        owned |= {
            t.task_id
            for t in await store.list_tasks(
                umo, statuses=("done", "dismissed"), limit=1000
            )
        }

    cleared = 0
    for job in await _cron.list_jobs("basic"):
        name = str(job.name or "")
        if not name.startswith(JOB_NAME_PREFIX):
            continue
        # campuscue:remind:<task_id>:<lead>
        parts = name.split(":")
        if umo is not None and (len(parts) < 4 or parts[-2] not in owned):
            continue
        # Left over from a previous run: non-persistent, so it is not on the
        # scheduler, but the row would otherwise accumulate forever.
        try:
            await _cron.delete_job(job.job_id)
            cleared += 1
        except Exception:  # noqa: BLE001
            logger.debug("[campuscue] could not clear job %s", job.job_id)

    tasks = 0
    reminders = 0
    for task in scoped:
        # The jobs were just cleared above, so the in-memory copy already has an
        # empty list; the *stored* row still carries the swept job ids until
        # something rewrites it. schedule_for_task only writes reminder_job_ids
        # when it actually scheduled something, so a task with no planable
        # reminder (deadline passed, deadline_reminders off, all leads inside
        # MIN_LEAD_SECONDS) would keep its stale ids and the board would report
        # "有提醒" for a task that owns no cron job. One failure must also not
        # abort the whole reconcile: everything after the failing task would
        # otherwise be left with its old jobs deleted and no new ones.
        try:
            planned = await schedule_for_task(task, now=now)
            if not planned:
                await store.update_task(task.task_id, reminder_job_ids=[])
        except Exception:  # noqa: BLE001 - one bad task must not lose the rest
            logger.exception(
                "[campuscue] resync failed for %s, reminders may be missing",
                task.task_id,
            )
        else:
            tasks += 1
            reminders += len(planned)

    logger.info(
        "[campuscue] reminder resync: %d task(s), %d reminder(s), %d stale cleared",
        tasks,
        reminders,
        cleared,
    )
    return {"tasks": tasks, "reminders": reminders, "cleared": cleared}


async def _known_umos() -> list[str]:
    """Every origin that has produced a task or been observed.

    Both halves are needed. Source rows are written when a message is observed,
    so a group that has only ever received hand-entered tasks -- a DM, or the
    board's 新建 before any extraction -- has none, and a startup resync driven by
    sources alone would leave those tasks with no alarms at all. Tasks are the
    thing being rescheduled, so they are the authoritative list; sources are kept
    because an observed group with nothing active yet costs one empty query and
    keeps this honest if the order ever inverts.
    """
    from sqlmodel import col, select

    from campuscue.models import CampusSource

    async with store.db_helper.get_db() as session:
        sources = await session.execute(select(col(CampusSource.umo)))
        tasks = await session.execute(
            select(col(CampusTask.umo)).where(
                col(CampusTask.status).in_(("active", "pending_confirm"))
            )
        )
        seen = {row for row in sources.scalars().all() if row}
        seen |= {row for row in tasks.scalars().all() if row}
    return sorted(seen)


__all__ = [
    "DEFAULT_LEADS",
    "JOB_NAME_PREFIX",
    "PlannedReminder",
    "bind",
    "cancel_for_task",
    "compose_message",
    "describe_lead",
    "is_bound",
    "plan_reminders",
    "push_context",
    "resync_all",
    "schedule_for_task",
]
