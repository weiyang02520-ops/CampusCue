"""ReminderScheduler (M3) — APScheduler integration, framework-isolated.

DB reminder facts are canonical; these jobs are fully derived runtime state
(10_REMINDER). Job ids are deterministic (`reminder:<id>`), so restart
reconstruction is idempotent even after scheduler memory wipe.

APScheduler 3.11.x verified API: AsyncIOScheduler.add_job(func, trigger,
..., id=..., replace_existing=True, misfire_grace_time=..., coalesce=...)
and shutdown(wait=...). All framework specifics stay in this module; the
service boundary (ReminderSchedulerBoundary) is what ReminderService sees.

Fire handler runs through an injected coroutine: re-reads latest DB state via
ReminderService.fire (defense in depth) — never delivers from stale memory.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger

from campuscue.services.reminder_service import ReminderSchedulerBoundary

logger = logging.getLogger("campuscue.services.reminder_scheduler")


class ReminderScheduler(ReminderSchedulerBoundary):
    """Owns the APScheduler runtime. Lifecycle: start()/shutdown().

    The scheduler is created STOPPED; jobs may be (re)installed before
    start() (startup resync), then start() begins firing. shutdown(wait=True)
    waits for in-flight fire handlers — no orphan background work.
    """

    def __init__(self, fire_callback) -> None:
        self._fire_callback = fire_callback  # async fn(reminder_id)
        # created STOPPED; add_job on a stopped AsyncIOScheduler is allowed —
        # jobs are picked up when start() is called (startup resync pattern)
        self._scheduler: AsyncIOScheduler | None = AsyncIOScheduler(timezone=timezone.utc)

    def start(self) -> None:
        if self._scheduler is None or self._scheduler.running:
            return
        self._scheduler.start()

    async def shutdown(self, *, wait: bool = True) -> None:
        sched = self._scheduler
        self._scheduler = None
        if sched is not None:
            try:
                sched.shutdown(wait=wait)
            except Exception:
                # APScheduler 3.11 raises SchedulerNotRunningError when the
                # scheduler was never started — treat as already-shut-down.
                pass

    @property
    def running(self) -> bool:
        return self._scheduler is not None and self._scheduler.running

    def job_count(self) -> int:
        if self._scheduler is None:
            return 0
        return len(self._scheduler.get_jobs())

    def get_job(self, job_id: str):
        if self._scheduler is None:
            return None
        return self._scheduler.get_job(job_id)

    # ------------------------------------------------------- boundary impl

    async def schedule(self, *, job_id: str, run_at: datetime, reminder_id: int) -> None:
        if self._scheduler is None:
            return  # shut down
        # APScheduler 3.11 memory jobstore: replace_existing appends instead of
        # replacing when the same id already exists. Explicit remove-then-add
        # gives the true idempotent-replace semantics (M3 §7).
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass
        self._scheduler.add_job(
            self._fire_callback,
            trigger=DateTrigger(run_date=run_at.astimezone(timezone.utc), timezone=timezone.utc),
            args=[reminder_id],
            id=job_id,
            name=f"campus-reminder-{reminder_id}",
            # APScheduler requires misfire_grace_time > 0 (or None); use the
            # minimal 1s — effective no-late-firing. Missed-downtime reminders
            # are additionally skipped by our own resync (explicit comparison),
            # so we never rely on scheduler misfire defaults.
            misfire_grace_time=1,
            coalesce=True,
            max_instances=1,
        )

    async def unschedule(self, job_id: str) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(job_id)
        except Exception:
            pass  # absent job -> no-op (idempotent)

    async def clear_all(self) -> None:
        if self._scheduler is None:
            return
        self._scheduler.remove_all_jobs()
