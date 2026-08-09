"""HTTP surface for the task board, mounted under /api/v1/campus.

Auth: these routes are unauthenticated by default, and that is a deliberate
choice for a locally-deployed single-student tool -- the board is served on
localhost alongside the bot, and requiring a dashboard login to see your own
homework would be friction with no security benefit on a machine only its owner
can reach. Set CAMPUSCUE_REQUIRE_AUTH=1 to put them behind the dashboard's
existing session check instead; anyone exposing this beyond localhost should.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlmodel import col, select
from starlette.responses import StreamingResponse

from astrbot.core import logger
from campuscue import store
from campuscue.api.events import hub
from campuscue.api.schemas import (
    BackupOut,
    CreateTaskIn,
    DeleteSourceOut,
    ExportOut,
    ImportIn,
    ImportOut,
    NotifyOut,
    NotifyTargetOut,
    NotifyTestOut,
    ProfileOut,
    ReminderOut,
    ReminderTestOut,
    RestoreIn,
    RestoreOut,
    SourceOut,
    StatsOut,
    TaskDetailOut,
    TaskOut,
    TraceOut,
    UpdateNotifyIn,
    UpdateProfileIn,
    UpdateSourceIn,
    UpdateTaskIn,
    short_umo,
)
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import CampusExtraction, CampusSource, CampusTask, as_utc

router = APIRouter(prefix="/campus", tags=["CampusCue"])

DEFAULT_UMO = os.environ.get("CAMPUSCUE_DEMO_UMO", "aiocqhttp:GroupMessage:demo-7788")
"""Whose board to show when the caller does not say. A single-student MVP has one
board; multi-user selection is a later concern."""

HEARTBEAT_SECONDS = 25.0
"""Keeps idle SSE connections alive through proxies that close quiet sockets."""


async def _maybe_require_auth(request: Request) -> None:
    """Enforce the dashboard session only when explicitly configured."""
    if os.environ.get("CAMPUSCUE_REQUIRE_AUTH", "").strip() not in ("1", "true", "yes"):
        return
    from astrbot.dashboard.api.auth import require_dashboard_user

    await require_dashboard_user(request)


# --- tasks ---------------------------------------------------------------


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    umo: str = Query(default=None),
    status: str = Query(
        default="active,pending_confirm",
        description="Comma-separated statuses",
    ),
    limit: int = Query(default=200, ge=1, le=1000),
    _: None = Depends(_maybe_require_auth),
) -> list[TaskOut]:
    statuses = tuple(s.strip() for s in status.split(",") if s.strip())
    if not statuses:
        # Explicitly empty means "all", matching the export endpoint's semantics
        # -- a caller that filters by status is never the one passing "".
        from campuscue.models import TASK_STATUSES

        statuses = TASK_STATUSES
    tasks = await store.list_tasks(umo or DEFAULT_UMO, statuses=statuses, limit=limit)
    return [TaskOut.of(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskDetailOut)
async def get_task(
    task_id: str,
    _: None = Depends(_maybe_require_auth),
) -> TaskDetailOut:
    task = await store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    trace = await store.get_task_trace(task_id)
    return TaskDetailOut(
        task=TaskOut.of(task), trace=[TraceOut.of(row) for row in trace]
    )


@router.post("/tasks", response_model=TaskOut)
async def create_task(
    payload: CreateTaskIn,
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> TaskOut:
    """Add a task by hand. Confidence 1.0 because a human asserted it."""
    target = umo or DEFAULT_UMO
    deadline = as_utc(payload.deadline)
    key = store.dedup_key(target, payload.title, deadline)

    # Same dedup the LLM tool path applies (campuscue/tools.py): a student
    # dictating a task that the pipeline already extracted, or double-clicking
    # 新建, must not create two sets of reminders for one obligation.
    async with store.db_helper.get_db() as session:
        existing = await store.find_duplicate(
            session, umo=target, key=key, now=datetime.now(timezone.utc)
        )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"该任务已存在（{existing.title}），未重复创建",
        )

    task = CampusTask(
        umo=target,
        title=payload.title,
        task_type=payload.task_type,
        status="active",
        deadline=deadline,
        location=payload.location,
        items=payload.items,
        detail=payload.detail,
        confidence=1.0,
        source_kind="manual",
        dedup_key=key,
    )
    task = await store.create_task(task)
    task = await _reschedule(task)
    out = TaskOut.of(task)
    hub.publish("task_created", out.model_dump(mode="json"))
    return out


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    payload: UpdateTaskIn,
    _: None = Depends(_maybe_require_auth),
) -> TaskOut:
    """Correct an extraction.

    Being able to fix a wrong deadline is the other half of the answer to "what
    if the AI is wrong" -- the trace explains, this repairs. A corrected deadline
    also re-derives the dedup key so the original notice cannot immediately
    re-create the task it was just edited out of.
    """
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="no fields to update")

    task = await store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    if "deadline" in fields:
        fields["deadline"] = as_utc(fields["deadline"])
        # A hand-set time is exact by definition.
        fields["deadline_is_explicit"] = True

    title = fields.get("title", task.title)
    deadline = fields.get("deadline", as_utc(task.deadline))
    fields["dedup_key"] = store.dedup_key(task.umo, title, deadline)

    updated = await store.update_task(task_id, **fields)
    assert updated is not None
    updated = await _reschedule(updated)
    out = TaskOut.of(updated)
    hub.publish("task_updated", out.model_dump(mode="json"))
    return out


async def _reschedule(task: CampusTask) -> CampusTask:
    """Bring a task's reminders in line with its current state.

    Called after every write. ``schedule_for_task`` cancels what the task already
    had before planning again, so this is safe to call unconditionally rather
    than working out whether the change actually affected the schedule -- and a
    status change to done/dismissed cancels without rescheduling.

    Failures never propagate: a reminder that could not be scheduled is a
    degraded task, but a 500 on the edit endpoint would leave the student unable
    to correct a wrong deadline at all.
    """
    try:
        from campuscue import reminders

        await reminders.schedule_for_task(task)
    except Exception:  # noqa: BLE001
        logger.exception("[campuscue] reschedule failed for %s", task.task_id)
        return task
    return await store.get_task(task.task_id) or task


async def _set_status(task_id: str, status: str, event: str) -> TaskOut:
    task = await store.update_task(task_id, status=status)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    task = await _reschedule(task)
    out = TaskOut.of(task)
    hub.publish(event, out.model_dump(mode="json"))
    return out


@router.post("/tasks/{task_id}/confirm", response_model=TaskOut)
async def confirm_task(task_id: str, _: None = Depends(_maybe_require_auth)) -> TaskOut:
    """Promote a low-confidence extraction to a real task."""
    return await _set_status(task_id, "active", "task_confirmed")


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
async def complete_task(
    task_id: str, _: None = Depends(_maybe_require_auth)
) -> TaskOut:
    return await _set_status(task_id, "done", "task_completed")


@router.post("/tasks/{task_id}/dismiss", response_model=TaskOut)
async def dismiss_task(task_id: str, _: None = Depends(_maybe_require_auth)) -> TaskOut:
    """Reject an extraction. Kept, not deleted, so the same notice cannot come
    straight back and so the false-positive rate stays measurable."""
    return await _set_status(task_id, "dismissed", "task_dismissed")


@router.post("/tasks/{task_id}/reopen", response_model=TaskOut)
async def reopen_task(task_id: str, _: None = Depends(_maybe_require_auth)) -> TaskOut:
    return await _set_status(task_id, "active", "task_updated")


# --- sources -------------------------------------------------------------


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(_: None = Depends(_maybe_require_auth)) -> list[SourceOut]:
    """Which groups CampusCue is watching, for the board's source picker.

    Groups whose only trace is a hand-created task also appear: the task exists,
    so the student must be able to navigate to it.

    The default umo is included only while no group is actually being watched. It
    exists so a fresh install has something to preselect; once a real group is
    there it would be an entry in the dropdown that the student never joined and
    cannot remove -- deleting it cannot drop a row that was never written. The
    condition matches ``/default-source``, so the picker always contains whatever
    the board falls back to.
    """
    sources = await store.list_sources()
    counts = await store.count_tasks_by_umo()

    out = [SourceOut.of(source, counts.get(source.umo, 0)) for source in sources]
    known = {item.umo for item in out}

    fallback = () if out else (DEFAULT_UMO,)
    for umo in (*fallback, *counts):
        if umo in known:
            continue
        out.append(
            SourceOut(
                umo=umo,
                label=short_umo(umo),
                open_tasks=counts.get(umo, 0),
                messages_seen=0,
            )
        )
        known.add(umo)
    return out


@router.get("/default-source", response_model=SourceOut)
async def default_source(_: None = Depends(_maybe_require_auth)) -> SourceOut:
    """The umo the other endpoints fall back to when the caller omits it.

    Exposed rather than hard-coded in the frontend because it comes from
    ``CAMPUSCUE_DEMO_UMO``: a board that assumed the built-in default would show
    an empty list on any machine that set that variable, which is exactly the
    machine a demo runs on.

    A watched group wins over the configured default. Otherwise the board would
    open on a session that ``/sources`` no longer lists, so the picker would show
    a group other than the one the board is actually displaying.
    """
    counts = await store.count_tasks_by_umo()
    sources = await store.list_sources()
    for source in sources:
        if source.umo == DEFAULT_UMO:
            return SourceOut.of(source, counts.get(DEFAULT_UMO, 0))
    if sources:
        return SourceOut.of(sources[0], counts.get(sources[0].umo, 0))
    return SourceOut(
        umo=DEFAULT_UMO,
        label=short_umo(DEFAULT_UMO),
        open_tasks=counts.get(DEFAULT_UMO, 0),
    )


@router.patch("/sources/{umo:path}", response_model=SourceOut)
async def patch_source(
    umo: str,
    payload: UpdateSourceIn,
    _: None = Depends(_maybe_require_auth),
) -> SourceOut:
    """Declare what a group is.

    ``{umo:path}`` rather than ``{umo}`` because a umo contains colons and, on
    some platforms, slashes; the default converter would truncate it at the first
    one and silently patch the wrong group.

    Setting ``course_name`` is not cosmetic: the L2 prompt renders it as 对应课程,
    so this is the one place in the product where a student's typing makes the
    extractor smarter rather than only correcting it afterwards.
    """
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要修改的字段")

    # Empty strings mean "clear this", not "set it to an empty label" -- the
    # SourceOut label chain falls through to short_umo() only on None.
    for key in ("display_name", "course_name"):
        if key in fields and isinstance(fields[key], str) and not fields[key].strip():
            fields[key] = None
        elif key in fields and isinstance(fields[key], str):
            fields[key] = fields[key].strip()

    source = await store.update_source(umo, **fields)
    counts = await store.count_tasks_by_umo()
    out = SourceOut.of(source, counts.get(umo, 0))
    hub.publish("source_updated", out.model_dump(mode="json"))
    return out


@router.delete("/sources/{umo:path}", response_model=DeleteSourceOut)
async def delete_source(
    umo: str,
    with_tasks: bool = Query(default=True),
    _: None = Depends(_maybe_require_auth),
) -> DeleteSourceOut:
    """Remove a watched group and, by default, everything extracted from it.

    Exists because a development database accumulates fixture groups, and every
    number on the board -- the L1 filter ratio above all -- is only meaningful if
    the groups behind it are real. Unlike dismissing a task this is a true delete:
    a fake group has no history worth keeping and leaving a disabled row behind
    would keep it in the picker forever.

    Reminders owned by the deleted tasks are cancelled here rather than in the
    store, which stays importable without the scheduler.
    """
    job_ids: list[str] = []
    removed = await store.delete_source(umo, with_tasks=with_tasks)
    job_ids = [str(j) for j in removed.get("job_ids", [])]

    cancelled = 0
    if job_ids:
        try:
            from campuscue import reminders as rem

            if rem._cron is not None:
                for job_id in job_ids:
                    try:
                        await rem._cron.delete_job(job_id)
                        cancelled += 1
                    except Exception:  # noqa: BLE001 - the cron table is a cache
                        logger.debug("[campuscue] job %s already gone", job_id)
        except Exception:  # noqa: BLE001
            logger.exception("[campuscue] could not cancel jobs for deleted source")

    out = DeleteSourceOut(
        umo=umo,
        tasks=int(removed.get("tasks", 0)),
        extractions=int(removed.get("extractions", 0)),
        reminders_cancelled=cancelled,
    )
    hub.publish("source_deleted", out.model_dump(mode="json"))
    logger.info(
        "[campuscue] deleted source %s (%d tasks, %d extractions, %d reminders)",
        umo,
        out.tasks,
        out.extractions,
        cancelled,
    )
    return out


# --- reminder preferences ------------------------------------------------


@router.get("/profile", response_model=ProfileOut)
async def get_profile(
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> ProfileOut:
    """Reminder preferences, materialised with defaults on first read."""
    return ProfileOut.of(await store.get_profile(umo or DEFAULT_UMO))


@router.patch("/profile", response_model=ProfileOut)
async def patch_profile(
    payload: UpdateProfileIn,
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> ProfileOut:
    """Change how early reminders fire, and when they stay quiet.

    Followed by a full resync: ``schedule_for_task`` reads the profile fresh on
    every call, so already-scheduled alarms keep their old lead times until
    something re-plans them. Without this, changing 提前一天 to 提前两天 would
    appear to work and change nothing for any task already on the board.
    """
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要修改的字段")

    target = umo or DEFAULT_UMO
    profile = await store.update_profile(target, **fields)

    # Same rationale as _reschedule: a scheduler that is not bound yet (tests,
    # or a board opened before on_astrbot_loaded) must not turn a saved
    # preference into a 500.
    if "lead_minutes" in fields or "quiet_hours" in fields:
        try:
            from campuscue import reminders

            await reminders.resync_all(target)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[CampusCue] 偏好保存后重排提醒失败: {exc}")

    out = ProfileOut.of(profile)
    hub.publish("profile_updated", out.model_dump(mode="json"))
    return out


# --- notification delivery ------------------------------------------------
#
# Global, not per-group: there is one student behind this process. See
# campuscue/notify.py for why detections go to a designated session instead of
# back into the group they were read from.


async def _notify_candidates(current: str) -> list[NotifyTargetOut]:
    """Everywhere a detection could usefully be sent, best first.

    The linked QQ account's private chat leads the list because it is the right
    answer for a real install: messages arrive on the student's phone and nobody
    else sees them. Watched groups follow so a study group that genuinely wants
    the notices can still be chosen, and the current setting is always present
    even when its platform is gone -- a picker that silently drops the saved value
    looks like it reset itself.
    """
    out: list[NotifyTargetOut] = []
    seen: set[str] = set()

    def add(umo: str, hint: str = "", recommended: bool = False) -> None:
        if not umo or umo in seen:
            return
        seen.add(umo)
        out.append(
            NotifyTargetOut(
                umo=umo, label=short_umo(umo), hint=hint, recommended=recommended
            )
        )

    # The student's own private chat is the right destination but not a
    # discoverable one: the only uin this process knows is the bot's own, and
    # qq:FriendMessage:<bot uin> is the bot messaging itself. So a private chat is
    # offered through friend_umo_prefix (typed as a QQ number) rather than
    # guessed here, and the enumerable candidates are the watched groups.
    add(current, hint="当前设置", recommended=bool(current))
    for source in await store.list_sources():
        add(source.umo, hint=source.display_name or source.course_name or "监听中的群")
    add(DEFAULT_UMO, hint="演示会话")
    return out


async def _notify_out(settings) -> NotifyOut:
    from campuscue.provision import PLATFORM_ID

    return NotifyOut(
        target_umo=settings.target_umo,
        target_label=short_umo(settings.target_umo) if settings.target_umo else "",
        on_detect=settings.on_detect,
        desktop_toast=settings.desktop_toast,
        deadline_reminders=settings.deadline_reminders,
        toast_supported=os.name == "nt",
        candidates=await _notify_candidates(settings.target_umo),
        friend_umo_prefix=f"{PLATFORM_ID}:FriendMessage:",
    )


@router.get("/notify", response_model=NotifyOut)
async def get_notify(_: None = Depends(_maybe_require_auth)) -> NotifyOut:
    """Current delivery settings plus everywhere they could point."""
    from campuscue import notify as nf

    return await _notify_out(await nf.get_settings())


@router.patch("/notify", response_model=NotifyOut)
async def patch_notify(
    payload: UpdateNotifyIn,
    _: None = Depends(_maybe_require_auth),
) -> NotifyOut:
    """Change where detections go, or turn a channel off.

    Turning ``deadline_reminders`` on or off resyncs: ``schedule_for_task``
    returns early while the switch is off, so every task created in the meantime
    has no alarm and flipping the switch would otherwise appear to work and
    change nothing until the next restart. Turning it *off* must cancel the
    alarms already sitting in the cron table -- a switch that reads as off but
    keeps firing at 09:00 is worse than no switch at all.
    """
    fields = payload.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="没有需要修改的字段")

    from campuscue import notify as nf

    settings = await nf.save_settings(**fields)

    if "deadline_reminders" in fields:
        try:
            from campuscue import reminders

            await reminders.resync_all()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[CampusCue] 修改到期提醒开关后重排失败: {exc}")

    out = await _notify_out(settings)
    hub.publish("notify_updated", out.model_dump(mode="json"))
    return out


@router.post("/notify/test", response_model=NotifyTestOut)
async def test_notify(_: None = Depends(_maybe_require_auth)) -> NotifyTestOut:
    """Send one sample detection through the real delivery path.

    A sample rather than a real task so the button works on an empty board, and
    through ``announce_detection`` rather than a bespoke push so a green result
    actually proves the production path -- including the desktop toast, which is
    the part most likely to be broken on a machine nobody has tested.
    """
    from campuscue import notify as nf

    sample = CampusTask(
        umo=DEFAULT_UMO,
        title="示例：提交软件工程实验三报告",
        task_type="homework",
        status="active",
        deadline=datetime.now(timezone.utc) + timedelta(days=1),
        location="线上提交",
        items=["实验报告", "源码压缩包"],
        confidence=1.0,
        source_kind="manual",
        source_group_name="课讯自检",
        source_sender_name="课讯",
        raw_text="这是一条自检消息，用来确认探测推送和电脑弹窗都通了。",
    )

    report = await nf.announce_detection(sample)
    detail = ""
    if report.skipped == "disabled":
        detail = "探测推送已关闭，先打开开关"
    elif report.skipped == "no_context":
        detail = "机器人还没连上（后端刚启动或未扫码）"
    elif report.errors:
        detail = report.errors[0]
    elif not report.pushed:
        detail = f"没有平台匹配 {report.target}"

    return NotifyTestOut(
        pushed=report.pushed,
        toasted=report.toasted,
        target=short_umo(report.target) if report.target else "",
        preview=nf.compose_detection(sample),
        detail=detail,
    )


# --- stats ---------------------------------------------------------------


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> StatsOut:
    target = umo or DEFAULT_UMO
    now = datetime.now(timezone.utc)
    local_now = now.astimezone(CAMPUS_TZ)
    end_of_today = local_now.replace(hour=23, minute=59, second=59).astimezone(
        timezone.utc
    )
    # The board's "七天内" metric is a rolling 7-day window, not the end of the
    # current calendar week -- naming it end_of_week would mislead the reader.
    in_seven_days = (local_now + timedelta(days=7)).astimezone(timezone.utc)

    async with store.db_helper.get_db() as session:
        counts = await session.execute(
            select(col(CampusTask.status), func.count())
            .where(col(CampusTask.umo) == target)
            .group_by(col(CampusTask.status))
        )
        by_status = dict(counts.all())

        async def count_where(*conditions) -> int:
            result = await session.execute(
                select(func.count())
                .select_from(CampusTask)
                .where(col(CampusTask.umo) == target)
                .where(col(CampusTask.status) == "active")
                .where(col(CampusTask.deadline).is_not(None))
                .where(*conditions)
            )
            return int(result.scalar() or 0)

        due_today = await count_where(
            col(CampusTask.deadline) >= now, col(CampusTask.deadline) <= end_of_today
        )
        due_week = await count_where(
            col(CampusTask.deadline) >= now, col(CampusTask.deadline) <= in_seven_days
        )
        overdue = await count_where(col(CampusTask.deadline) < now)

        source_row = await session.execute(
            select(CampusSource).where(col(CampusSource.umo) == target)
        )
        source = source_row.scalars().first()

    seen = source.stat_seen if source else 0
    passed = source.stat_l1_passed if source else 0
    created = source.stat_tasks_created if source else 0

    return StatsOut(
        total_active=by_status.get("active", 0),
        total_pending_confirm=by_status.get("pending_confirm", 0),
        due_today=due_today,
        due_this_week=due_week,
        overdue=overdue,
        messages_seen=seen,
        messages_through_l1=passed,
        tasks_created=created,
        l1_filtered_ratio=round(1 - passed / seen, 4) if seen else 0.0,
    )


# --- live stream ---------------------------------------------------------


@router.get("/stream")
async def stream(
    request: Request,
    _: None = Depends(_maybe_require_auth),
) -> StreamingResponse:
    """Server-sent events: task_created, task_updated, task_confirmed, ..."""
    queue = hub.subscribe()

    async def generator():
        # An immediate comment flushes headers so the browser fires onopen
        # rather than waiting for the first real event.
        yield ": connected\n\n"
        try:
            while True:
                # Race the next event against the client going away. Waiting on
                # queue.get() alone would keep a dead tab subscribed for up to
                # HEARTBEAT_SECONDS after it closed; is_disconnected() answers
                # immediately when the transport is gone.
                get_task = asyncio.create_task(queue.get())
                gone_task = asyncio.create_task(request.is_disconnected())
                try:
                    done, _ = await asyncio.wait(
                        {get_task, gone_task},
                        timeout=HEARTBEAT_SECONDS,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if gone_task in done and gone_task.result():
                        break
                    if get_task in done:
                        body = get_task.result()
                        # A client that closed between the wait and the write
                        # makes yield raise (Starlette re-raises the broken-pipe
                        # as a generator exception); leaving it uncaught can
                        # spin the loop on a dead socket.
                        yield f"data: {body}\n\n"
                        continue
                    # Neither completed: heartbeat to keep proxies and the
                    # browser's own timeout honest.
                    yield ": keepalive\n\n"
                except (GeneratorExit, ConnectionError, OSError, RuntimeError):
                    # The transport is gone. Swallow and exit -- the finally
                    # below unsubscribes the queue.
                    break
                finally:
                    # The loser must not linger: an abandoned get() task would
                    # hold a slot on the hub queue forever.
                    get_task.cancel()
                    gone_task.cancel()
                    await asyncio.gather(get_task, gone_task, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        finally:
            hub.unsubscribe(queue)
            logger.debug("[campuscue] SSE client gone, %d left", hub.subscriber_count)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx buffers streamed responses by default, which defeats SSE.
            "X-Accel-Buffering": "no",
        },
    )


# --- recent extractions (debug / credibility view) -----------------------


@router.get("/extractions", response_model=list[TraceOut])
async def recent_extractions(
    umo: str = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(_maybe_require_auth),
) -> list[TraceOut]:
    """Every extraction attempt, including the rejections.

    Showing the negatives is the point: a board that only lists successes proves
    nothing about how often the model is wrong.
    """
    target = umo or DEFAULT_UMO
    async with store.db_helper.get_db() as session:
        result = await session.execute(
            select(CampusExtraction)
            .where(col(CampusExtraction.umo) == target)
            .order_by(col(CampusExtraction.created_at).desc())
            .limit(limit)
        )
        rows = list(result.scalars().all())
    return [TraceOut.of(row) for row in rows]


# --- reminders -----------------------------------------------------------


@router.get("/reminders", response_model=list[ReminderOut])
async def list_reminders(
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> list[ReminderOut]:
    """The reminders actually on the scheduler, read from the cron table.

    Not recomputed from the tasks: the value of this endpoint is proving that the
    alarms exist, and a computed list would show what *should* be scheduled even
    when nothing is. Empty means the scheduler is not bound, which is the honest
    answer during a replay-only session.
    """
    from campuscue import reminders as rem

    target = umo or DEFAULT_UMO
    tasks = {
        task.task_id: task
        for task in await store.list_tasks(
            target, statuses=("active", "pending_confirm")
        )
    }
    if not rem.is_bound() or rem._cron is None:
        return []

    out: list[ReminderOut] = []
    for job in await rem._cron.list_jobs("basic"):
        if not str(job.name or "").startswith(rem.JOB_NAME_PREFIX):
            continue
        payload = job.payload if isinstance(job.payload, dict) else {}
        task = tasks.get(str(payload.get("task_id") or ""))
        if task is None:
            continue
        out.append(
            ReminderOut(
                job_id=job.job_id,
                task_id=task.task_id,
                task_title=task.title,
                label=str(payload.get("label") or ""),
                fire_at=as_utc(job.next_run_time),
                status=job.status or "scheduled",
            )
        )
    out.sort(key=lambda r: (r.fire_at is None, r.fire_at))
    return out


@router.post("/tasks/{task_id}/remind-now", response_model=ReminderTestOut)
async def remind_now(
    task_id: str, _: None = Depends(_maybe_require_auth)
) -> ReminderTestOut:
    """Fire this task's reminder immediately, through the real delivery path.

    Exists for the demo and for setup. "The reminder will arrive tomorrow at
    09:00" is unverifiable in a five-minute pitch and unverifiable when a student
    is checking their NapCat connection works; this pushes the same composed
    message through the same ``send_message`` call the scheduler would use, so a
    successful test means the scheduled one will work too.
    """
    from astrbot.core.message.message_event_result import MessageChain
    from campuscue import reminders as rem

    task = await store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")

    text = rem.compose_message(task, "测试推送")
    if not rem.is_bound():
        return ReminderTestOut(delivered=False, preview=text, detail="调度器未就绪")

    try:
        delivered = await rem._ctx.send_message(task.umo, MessageChain().message(text))
    except Exception as exc:  # noqa: BLE001 - report, don't 500
        logger.exception("[campuscue] test push failed for task %s", task.task_id)
        return ReminderTestOut(delivered=False, preview=text, detail=repr(exc))

    return ReminderTestOut(
        delivered=bool(delivered),
        preview=text,
        detail="" if delivered else f"没有平台匹配 {task.umo}",
    )


# --- import / export -----------------------------------------------------


@router.get("/backup", response_model=BackupOut)
async def export_full_backup(
    _: None = Depends(_maybe_require_auth),
) -> BackupOut:
    """Export every CampusCue-owned table, but no host credentials or sessions."""
    from campuscue.api import backup

    out = await backup.export_backup()
    logger.info(
        "[campuscue] full backup exported: %d tasks, %d sources, %d extractions",
        len(out.tasks),
        len(out.sources),
        len(out.extractions),
    )
    return out


@router.post("/restore", response_model=RestoreOut)
async def restore_full_backup(
    payload: RestoreIn,
    _: None = Depends(_maybe_require_auth),
) -> RestoreOut:
    """Atomically replace CampusCue data, then rebuild machine-local reminders."""
    from campuscue import reminders
    from campuscue.api import backup

    out = await backup.replace_from_backup(payload)
    try:
        reminder_report = await reminders.resync_all()
        out.reminders = reminder_report["reminders"]
    except Exception:  # noqa: BLE001 - restored data remains valid without scheduler
        logger.exception("[campuscue] reminder rebuild failed after full restore")
        out.detail = "数据已恢复，但提醒重建失败；重启课讯后会自动重建"

    hub.publish("backup_restored", out.model_dump(mode="json"))
    logger.info(
        "[campuscue] full backup restored: %d tasks, %d sources, %d extractions",
        out.tasks,
        out.sources,
        out.extractions,
    )
    return out


@router.get("/export", response_model=ExportOut)
async def export_tasks(
    umo: str = Query(default=None),
    status: str = Query(default="", description="Comma-separated statuses"),
    _: None = Depends(_maybe_require_auth),
) -> ExportOut:
    """Hand back the tasks as one JSON document.

    No ``umo`` means every group, and no ``status`` means every status --
    deliberately wider defaults than /tasks uses. That endpoint answers "what am
    I looking at now", where narrowing is the point; this one answers "give me my
    data", where a silent narrowing would be a backup that quietly lost most of
    it.
    """
    from campuscue.api import transfer

    statuses = tuple(s.strip() for s in status.split(",") if s.strip())
    out = await transfer.export_tasks(umo=umo or None, statuses=statuses)
    logger.info(
        "[campuscue] exported %d tasks from %d group(s)", out.count, len(out.umos)
    )
    return out


@router.post("/import", response_model=ImportOut)
async def import_tasks(
    payload: ImportIn,
    _: None = Depends(_maybe_require_auth),
) -> ImportOut:
    """Take a document back in, then re-plan the reminders it implies.

    Rescheduling is not optional book-keeping: reminder job ids do not travel in
    the file (they name rows in the writing machine's cron table), so an import
    that only wrote rows would produce tasks with deadlines and no alarms -- the
    one failure a student would not notice until the deadline passed.
    """
    from campuscue.api import transfer

    report = await transfer.apply_import(
        payload.tasks,
        default_umo=DEFAULT_UMO,
        force_umo=payload.umo,
        overwrite=payload.overwrite,
    )

    planned = 0
    for task_id in [*report.created, *report.updated]:
        task = await store.get_task(task_id)
        if task is None:  # pragma: no cover - written in the same transaction
            continue
        task = await _reschedule(task)
        # Counts tasks that came out of it with an alarm, not jobs: a task with
        # three lead times is still one thing the student will be reminded about,
        # and past-deadline or done tasks correctly contribute nothing.
        if task.reminder_job_ids:
            planned += 1

    detail = ""
    if not payload.tasks:
        detail = "文件里没有任务"
    elif not report.created and not report.updated:
        detail = f"{report.skipped} 条都已经在这里了，没有变化"

    out = ImportOut(
        created=len(report.created),
        updated=len(report.updated),
        skipped=report.skipped,
        reminders_planned=planned,
        umos=sorted(report.umos),
        detail=detail,
    )
    # The board is a live view; an import that changed nothing on screen until
    # the next manual refresh would look like it failed.
    hub.publish("tasks_imported", out.model_dump(mode="json"))
    logger.info(
        "[campuscue] imported tasks: %d new, %d updated, %d skipped, %d reminders",
        out.created,
        out.updated,
        out.skipped,
        planned,
    )
    return out


__all__ = ["DEFAULT_UMO", "router"]
