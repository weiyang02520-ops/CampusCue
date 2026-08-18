"""TaskService (M2b.1 + M3) — the ONLY business task-creation/mutation path.

Owns: candidate validation, AUTHORITATIVE dedup recheck (inside a process-local
lock critical section), status application from the pipeline-provided
candidate.pending_confirm, task construction, DB create, and M3 lifecycle
mutations (deadline change / complete / dismiss / delete) with reminder
coupling (ADR-006: reminder lifecycle orchestration lives HERE).

M2b.1.1 (Finding 13): status determination (confidence vs threshold, deadline
resolution) lives in the Pipeline (L4/L6); TaskService does NOT recompute
confidence and holds no threshold of its own.

M3: Reminder integration is OPTIONAL/INJECTED (reminder_service param). When
absent, task create/mutate still works exactly as M2 — no placeholder Reminder
objects, no M2 regression.

Concurrent safety: a single process-local asyncio.Lock serializes
dedup-recheck + insert. Same-source-message DB UNIQUE remains final defense.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from campuscue.repositories.repositories import (
    DuplicateError,
    NotFoundError,
    TaskRepository,
)
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import TaskCategory, TaskPriority, TaskStatus
from campuscue.storage.models import Task
from campuscue.tasks.dedup import Deduplicator
from campuscue.tasks.models import TaskCandidate


# Public service-boundary sentinel: omitted deadline is distinct from an
# explicit ``None`` which clears the deadline.
DEADLINE_UNSET: Final = object()


@dataclass(frozen=True)
class TaskCreationResult:
    created: bool
    task: Task | None = None
    reason: str = ""  # duplicate reason when not created


class TaskService:
    def __init__(
        self,
        tasks: TaskRepository,
        *,
        clock: Clock | None = None,
        reminder_service=None,  # optional injected M3 coupling
    ) -> None:
        self._tasks = tasks
        self._clock = clock or SystemClock()
        self._lock = asyncio.Lock()
        self._dedup = Deduplicator(tasks, clock=self._clock)
        self._reminders = reminder_service  # None -> reminder subsystem disabled

    async def create_task(self, candidate: TaskCandidate) -> TaskCreationResult:
        """Authoritative create. Serialized by the process-local lock:
        dedup recheck + insert happen inside the critical section."""
        async with self._lock:
            # recheck dedup INSIDE the critical section (semantic + strongest)
            dedup = await self._dedup.check(
                source_id=candidate.source_id,
                source_message_id=candidate.source_message_id,
                title=candidate.title,
                course=candidate.course,
                deadline=candidate.deadline,
            )
            if dedup.is_duplicate:
                return TaskCreationResult(
                    created=False, reason=dedup.reason, task=None
                )
            status = (
                TaskStatus.PENDING_CONFIRM.value
                if candidate.pending_confirm
                else TaskStatus.PENDING.value
            )
            try:
                task = await self._tasks.create(
                    title=candidate.title,
                    description=candidate.description,
                    category=candidate.category,
                    course=candidate.course,
                    deadline=candidate.deadline,
                    status=status,
                    priority=TaskPriority.NORMAL.value,
                    confidence=candidate.confidence,
                    dedup_key=candidate.dedup_key,
                    source_id=candidate.source_id,
                    source_message_id=candidate.source_message_id,
                    source_text_reference=candidate.source_text_reference,
                )
            except DuplicateError:
                # DB UNIQUE final defense (concurrent same-message)
                return TaskCreationResult(
                    created=False, reason="same_source_message", task=None
                )
            # M3: plan reminders for active pending tasks with deadline
            if self._reminders is not None and task.status == TaskStatus.PENDING.value:
                await self._reminders.plan_reminders(task)
            return TaskCreationResult(created=True, task=task, reason="created")

    # ------------------------------------------------------------ M3 mutations

    async def change_deadline(self, task_id: int, deadline: datetime | None) -> Task:
        """Update task deadline; old reminder plan is replaced by a new one
        (plan_reminders is idempotent: cancel old -> install new)."""
        if deadline is not None and deadline.tzinfo is None:
            raise ValueError("naive deadline rejected")
        async with self._lock:
            task = await self._tasks.get(task_id)
            if task.status != TaskStatus.PENDING.value:
                raise ValueError(f"cannot change deadline of task in status {task.status!r}")
            task = await self._tasks.update_deadline(task_id, deadline)
            if self._reminders is not None:
                await self._reminders.plan_reminders(task)
            return task

    async def complete(self, task_id: int) -> Task:
        """Complete task -> done; active reminders cancelled."""
        async with self._lock:
            task = await self._tasks.set_status(task_id, TaskStatus.DONE.value)
            if self._reminders is not None:
                await self._reminders.cancel_for_task(task_id)
            return task

    async def dismiss(self, task_id: int) -> Task:
        """Dismiss task -> dismissed; active reminders cancelled."""
        async with self._lock:
            task = await self._tasks.set_status(task_id, TaskStatus.DISMISSED.value)
            if self._reminders is not None:
                await self._reminders.cancel_for_task(task_id)
            return task

    async def delete(self, task_id: int) -> None:
        """Delete task (FK-safe: reminder rows hard-deleted first)."""
        async with self._lock:
            if self._reminders is not None:
                # hard-delete reminder facts + drop derived jobs before task row
                await self._reminders.cancel_for_task(task_id)
                await self._reminders.delete_reminders_for_task(task_id)
            await self._tasks.delete(task_id)

    # ------------------------------------------------ M4 source-scoped tools

    async def list_for_source(
        self,
        source_id: int,
        *,
        scope: str | None = None,
        now: datetime | None = None,
        tz=None,
    ) -> list[Task]:
        """M4 §17-18: source-scoped read for Agent tools (task_list).

        Scope semantics (explicit + tested):
          open     pending + pending_confirm (unfinished)      [default]
          pending  pending only
          done     done only
          overdue  unfinished with deadline < now (injected clock)
          today    unfinished with deadline within the LOCAL calendar day
          week     unfinished with deadline in [now, now + 7 days)
        Scoped queries filter in SERVICE code on top of the source-scoped
        repository query — the global TaskRepository list is never exposed.
        """
        tasks = await self._tasks.list_for_source(source_id)
        if scope is None or scope == "open":
            wanted = {TaskStatus.PENDING.value, TaskStatus.PENDING_CONFIRM.value}
            return [t for t in tasks if t.status in wanted]
        if scope == "pending":
            wanted = {TaskStatus.PENDING.value}
            return [t for t in tasks if t.status in wanted]
        if scope == "done":
            return [t for t in tasks if t.status == TaskStatus.DONE.value]
        if scope == "dismissed":
            return [t for t in tasks if t.status == TaskStatus.DISMISSED.value]
        if scope in ("overdue", "today", "week"):
            unfinished = {TaskStatus.PENDING.value, TaskStatus.PENDING_CONFIRM.value}
            now_local = (now or self._clock.utcnow()).astimezone(tz) if tz is not None else (now or self._clock.utcnow())
            result: list[Task] = []
            for t in tasks:
                if t.status not in unfinished or t.deadline is None:
                    continue
                dl_local = t.deadline.astimezone(tz) if tz is not None else t.deadline
                if scope == "overdue":
                    if dl_local < now_local:
                        result.append(t)
                elif scope == "today":
                    if dl_local.date() == now_local.date():
                        result.append(t)
                elif scope == "week":
                    from datetime import timedelta

                    if now_local <= dl_local < now_local + timedelta(days=7):
                        result.append(t)
            return result
        raise ValueError(f"unsupported task_list scope: {scope!r}")

    async def get_for_source(self, source_id: int, task_id: int) -> Task:
        """M4 §19: source-scoped get. A foreign task id MUST NOT reveal whether
        the task exists (no cross-source existence leak) — NotFoundError."""
        task = await self._tasks.get(task_id)  # NotFoundError if truly absent
        if task.source_id != source_id:
            raise NotFoundError(f"task {task_id} not found")
        return task

    async def update_task(
        self,
        source_id: int,
        task_id: int,
        *,
        title: str | None = None,
        course: str | None = None,
        deadline: datetime | None | object = DEADLINE_UNSET,
    ) -> Task:
        """M4 §21: source-scoped field update through the single business gate.

        deadline=DEADLINE_UNSET means "leave unchanged"; deadline=None clears
        the deadline. Any deadline CHANGE rebuilds the reminder plan (M3
        coupling preserved — no second mutation pathway inside tools)."""
        has_any = title is not None or course is not None or deadline is not DEADLINE_UNSET
        if not has_any:
            raise ValueError("no fields to update")
        if title is not None and not title.strip():
            raise ValueError("title must not be empty")
        if deadline is not DEADLINE_UNSET and deadline is not None and deadline.tzinfo is None:
            raise ValueError("naive deadline rejected")
        async with self._lock:
            task = await self._tasks.get(task_id)
            if task.source_id != source_id:
                raise NotFoundError(f"task {task_id} not found")
            if task.status != TaskStatus.PENDING.value:
                raise ValueError(
                    f"only pending tasks can be updated (status {task.status!r})"
                )
            deadline_changed = (
                deadline is not DEADLINE_UNSET and deadline != task.deadline
            )
            new_deadline = deadline if deadline is not DEADLINE_UNSET else task.deadline
            task = await self._tasks.update_fields(
                task_id,
                title=title,
                course=course,
                deadline=new_deadline,
            )
            # M3 lifecycle: any deadline change rebuilds the reminder plan
            if deadline_changed and self._reminders is not None:
                await self._reminders.plan_reminders(task)
            return task


def candidate_description(*, submission_method: str | None, reason: str | None) -> str | None:
    """Compact human-readable description. submission_method preserved here
    (CURRENT M2 LIMITATION: no dedicated Task column; also kept in audit)."""
    parts: list[str] = []
    if submission_method:
        parts.append(f"提交方式：{submission_method}")
    if reason:
        parts.append(f"识别依据：{reason}")
    return "；".join(parts) if parts else None
