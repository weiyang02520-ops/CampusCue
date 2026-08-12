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

from campuscue.repositories.repositories import DuplicateError, TaskRepository
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import TaskCategory, TaskPriority, TaskStatus
from campuscue.storage.models import Task
from campuscue.tasks.dedup import Deduplicator
from campuscue.tasks.models import TaskCandidate


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


def candidate_description(*, submission_method: str | None, reason: str | None) -> str | None:
    """Compact human-readable description. submission_method preserved here
    (CURRENT M2 LIMITATION: no dedicated Task column; also kept in audit)."""
    parts: list[str] = []
    if submission_method:
        parts.append(f"提交方式：{submission_method}")
    if reason:
        parts.append(f"识别依据：{reason}")
    return "；".join(parts) if parts else None
