"""TaskService (M2b.1) — the ONLY business task-creation path.

Owns: candidate validation, AUTHORITATIVE dedup recheck (inside a process-local
lock critical section), status selection, task construction, DB create.
Pipeline must not call TaskRepository.create() directly.

Concurrent safety: a single process-local asyncio.Lock serializes
dedup-recheck + insert. Same-source-message DB UNIQUE remains final defense.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

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
        confidence_threshold: float = 0.6,
    ) -> None:
        self._tasks = tasks
        self._clock = clock or SystemClock()
        self._confidence_threshold = confidence_threshold
        self._lock = asyncio.Lock()
        self._dedup = Deduplicator(tasks, clock=self._clock)

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
            return TaskCreationResult(created=True, task=task, reason="created")


def decide_pending_confirm(*, confidence: float, deadline: object | None, deadline_resolved: bool) -> bool:
    """Status selection (M2b.1 §34):

    pending when confidence >= threshold AND deadline is resolved (or absent
    where confirmation is not useful). pending_confirm when confidence low OR
    deadline was stated but failed to resolve.
    """
    if confidence < 0.6:
        return True
    if deadline is not None and not deadline_resolved:
        return True
    return False


def candidate_description(*, submission_method: str | None, reason: str | None) -> str | None:
    """Compact human-readable description. submission_method preserved here
    (CURRENT M2 LIMITATION: no dedicated Task column; also kept in audit)."""
    parts: list[str] = []
    if submission_method:
        parts.append(f"提交方式：{submission_method}")
    if reason:
        parts.append(f"识别依据：{reason}")
    return "；".join(parts) if parts else None
