"""ReminderService (M3) — owns reminder BUSINESS rules.

Core invariant (ADR-006 / 10_REMINDER): DB reminder rows are canonical FACTS;
scheduler jobs are DERIVED runtime state, rebuildable from facts via resync.

Owns:
- plan_reminders(task): idempotent plan for one task (cancel old -> compute
  desired -> persist facts)
- cancel_for_task(task_id): lifecycle cancellation (complete/dismiss/delete)
- resync_all(): rebuild derived scheduler state from DB facts
- fire(reminder_id): re-check latest task state, then deliver (or skip)

Pure policy (planning offsets / quiet-hours folding / MIN_LEAD_SECONDS) lives
in reminder_policy.py, fully testable with fixed clock + timezone.

ReminderService does NOT touch the scheduler directly — it delegates derived
job (re)building to an injected scheduler boundary so the service stays
scheduler-framework-agnostic and tests can inject a fake.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from campuscue.repositories.repositories import ReminderRepository, TaskRepository
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import ReminderStatus, TaskStatus
from campuscue.storage.models import Reminder, Task
from campuscue.tasks.reminder_policy import (
    DEFAULT_POLICY,
    DesiredReminder,
    plan_desired_reminders,
)

logger = logging.getLogger("campuscue.services.reminder")


@dataclass(frozen=True)
class ReminderPlanResult:
    """Result of one plan_reminders call (audit/safe reporting)."""

    task_id: int
    planned: int  # newly created reminder fact rows
    cancelled_previous: int  # old scheduled facts cancelled
    desired: list[DesiredReminder]  # what SHOULD be scheduled (for scheduler)


class ReminderSchedulerBoundary:
    """Minimal platform-neutral boundary for DERIVED scheduler jobs.

    ReminderService depends on this abstraction, not on APScheduler. The real
    APScheduler-backed implementation lives in reminder_scheduler.py; tests
    inject a fake.
    """

    async def schedule(self, *, job_id: str, run_at: datetime, reminder_id: int) -> None:
        """Idempotently (re)install one derived job for a reminder fact."""

    async def unschedule(self, job_id: str) -> None:
        """Remove one derived job (no-op if absent)."""

    async def clear_all(self) -> None:
        """Drop all derived jobs (full resync path)."""


class NoopScheduler(ReminderSchedulerBoundary):
    """Fallback boundary: no derived scheduling (reminder subsystem disabled)."""

    async def schedule(self, *, job_id: str, run_at: datetime, reminder_id: int) -> None:
        pass

    async def unschedule(self, job_id: str) -> None:
        pass

    async def clear_all(self) -> None:
        pass


def reminder_job_id(reminder_id: int) -> str:
    """Deterministic stable scheduler job id for a reminder fact (M3 §7).

    Same DB reminder id always maps to the same logical job id, so restart
    reconstruction is idempotent even if APScheduler memory was wiped.
    """
    return f"reminder:{reminder_id}"


class ReminderService:
    def __init__(
        self,
        reminders: ReminderRepository,
        tasks: TaskRepository,
        *,
        scheduler: ReminderSchedulerBoundary | None = None,
        clock: Clock | None = None,
        timezone: ZoneInfo | None = None,
        policy: object | None = None,
    ) -> None:
        self._reminders = reminders
        self._tasks = tasks
        self._scheduler = scheduler or NoopScheduler()
        self._clock = clock or SystemClock()
        self._tz = timezone or ZoneInfo("Asia/Shanghai")
        self._policy = policy or DEFAULT_POLICY

    # ---------------------------------------------------------------- planning

    async def plan_reminders(self, task: Task) -> ReminderPlanResult:
        """IDEMPOTENT plan for one task (ADR-006 lifecycle entry).

        Cancel old active facts -> compute desired -> persist new facts ->
        (scheduler derives jobs via boundary). Repeated calls never create
        duplicate facts or jobs.
        """
        cancelled = await self._reminders.cancel_for_task(task.id, now=self._clock.utcnow())
        desired = plan_desired_reminders(
            task=task,
            now=self._clock.utcnow(),
            tz=self._tz,
            policy=self._policy,
        )
        created = 0
        for d in desired:
            await self._reminders.create(
                task_id=task.id,
                trigger_at=d.trigger_at_utc,
                type=d.type,
            )
            created += 1
        # derived jobs follow the persisted facts (idempotent replace semantics)
        scheduled = await self._reminders.list_scheduled()
        await self._scheduler.clear_all()
        for r in scheduled:
            await self._scheduler.schedule(
                job_id=reminder_job_id(r.id), run_at=r.trigger_at, reminder_id=r.id
            )
        return ReminderPlanResult(
            task_id=task.id, planned=created, cancelled_previous=cancelled, desired=desired
        )

    async def cancel_for_task(self, task_id: int) -> int:
        """Cancel all active reminder facts + derived jobs for a task."""
        cancelled = await self._reminders.cancel_for_task(task_id, now=self._clock.utcnow())
        for r in await self._reminders.list_for_task(task_id):
            if r.status == ReminderStatus.CANCELLED.value:
                await self._scheduler.unschedule(reminder_job_id(r.id))
        return cancelled

    async def delete_reminders_for_task(self, task_id: int) -> int:
        """HARD-delete reminder facts + drop derived jobs (FK-safe task delete)."""
        for r in await self._reminders.list_for_task(task_id):
            await self._scheduler.unschedule(reminder_job_id(r.id))
        return await self._reminders.delete_for_task(task_id)

    async def resync_all(self) -> int:
        """REBUILD derived scheduler state from canonical DB facts.

        - scheduler memory starts empty after restart
        - reads all SCHEDULED reminder facts
        - skips facts whose trigger is already in the past (missed while down:
          MUST NOT fire/backfill; close them as cancelled with a safe error note)
        - skips facts whose task is no longer active (done/dismissed/deleted)
        - (re)installs deterministic jobs for the survivors
        - returns number of jobs installed (for tests/audit)
        """
        scheduled = await self._reminders.list_scheduled()
        now = self._clock.utcnow()
        installed = 0
        for r in scheduled:
            valid = True
            try:
                task = await self._tasks.get(r.task_id)
            except Exception:
                # task deleted -> close fact, no job
                valid = False
                task = None
            if valid and task is not None:
                valid = task.status == TaskStatus.PENDING.value
            if not valid:
                await self._reminders.mark_cancelled(r.id, now=now)
                continue
            if r.trigger_at <= now:
                # missed while down: do NOT backfill; close fact safely
                await self._reminders.mark_cancelled(r.id, now=now)
                continue
            await self._scheduler.schedule(
                job_id=reminder_job_id(r.id), run_at=r.trigger_at, reminder_id=r.id
            )
            installed += 1
        return installed

    async def fire(self, reminder_id: int) -> bool:
        """Due reminder handler. Re-checks LATEST task state (defense in depth,
        §15): task must still exist, be pending, and reminder still scheduled.
        Returns True when a delivery callback was invoked."""
        try:
            reminder = await self._reminders.get(reminder_id)
        except Exception:
            return False
        if reminder.status != ReminderStatus.SCHEDULED.value:
            return False
        try:
            task = await self._tasks.get(reminder.task_id)
        except Exception:
            # task deleted -> close fact, no delivery
            await self._reminders.mark_cancelled(reminder_id, now=self._clock.utcnow())
            return False
        if task.status != TaskStatus.PENDING.value:
            # done/dismissed -> close fact, no delivery
            await self._reminders.mark_cancelled(reminder_id, now=self._clock.utcnow())
            return False
        await self._reminders.mark_fired(reminder_id, run_at=self._clock.utcnow())
        # platform-neutral delivery boundary (injected; M3 tests use fake sink)
        await self._deliver(reminder, task)
        return True

    async def _deliver(self, reminder: Reminder, task: Task) -> None:
        """Injected delivery sink. M3 ships a NoopDelivery (no end-user UX
        claim); real QQ/desktop delivery is a later milestone."""
        if self._delivery is not None:
            await self._delivery.deliver(reminder=reminder, task=task)

    def set_delivery(self, delivery) -> None:
        self._delivery = delivery

    # ---------------------------------------------------------------- helper

    async def list_for_task(self, task_id: int) -> list[Reminder]:
        return await self._reminders.list_for_task(task_id)


class NoopDelivery:
    """M3 default: no end-user delivery (real notification UX not in M3 scope).
    Fire tests inject a fake sink."""

    async def deliver(self, *, reminder: Reminder, task: Task) -> None:
        pass
