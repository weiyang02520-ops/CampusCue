"""Task Extraction Pipeline (M2b.1) — L0..L7 orchestration.

CampusEvent -> L0 SourcePolicy -> L1 Prefilter -> L2 ContextCollector ->
L3 TaskExtractor -> L4 TimeNormalizer -> L5 Deduplicator -> L6 Confidence ->
L7 TaskService -> SQLite.

Privacy: L0/L1 rejections create NO Extraction rows (avoid implicit chat
history). L1-passing candidates always terminate in exactly one Extraction row.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from campuscue.core.events import CampusEvent
from campuscue.providers.errors import (
    NoProviderConfiguredError,
    ProviderError,
    ProviderErrorCode,
)
from campuscue.repositories.repositories import ExtractionRepository, SourceRepository
from campuscue.services.task_service import (
    TaskCreationResult,
    TaskService,
    candidate_description,
)
from campuscue.storage.clock import Clock, SystemClock
from campuscue.storage.enums import ExtractionStatus
from campuscue.storage.models import Extraction, Task
from campuscue.tasks.context import ContextCollector
from campuscue.tasks.dedup import Deduplicator, normalize_title
from campuscue.tasks.extractor import ExtractionError, TaskExtractor
from campuscue.tasks.models import (
    DedupResult,
    ExtractedTask,
    ExtractionResult,
    PrefilterResult,
    SourcePolicyResult,
    TaskCandidate,
)
from campuscue.tasks.prefilter import prefilter
from campuscue.tasks.source_policy import SourcePolicy
from campuscue.tasks.time_normalizer import resolve_deadline

logger = logging.getLogger("campuscue.tasks.pipeline")

CONFIDENCE_THRESHOLD = 0.6


@dataclass
class PipelineOutcome:
    """Terminal outcome of one pipeline run (audit-safe)."""

    kind: str  # model_said_none | task_created | pending_confirm | duplicate | provider_error | parse_error | normalization_error | l0_drop | l1_drop
    task_id: int | None = None
    dedup_reason: str = ""
    structured_mode: str = ""


class TaskPipeline:
    def __init__(
        self,
        *,
        sources: SourceRepository,
        extractions: ExtractionRepository,
        task_service: TaskService,
        provider_manager,
        timezone: ZoneInfo,
        clock: Clock | None = None,
        confidence_threshold: float = CONFIDENCE_THRESHOLD,
    ) -> None:
        self._sources = sources
        self._extractions = extractions
        self._task_service = task_service
        self._provider_manager = provider_manager
        self._tz = timezone
        self._clock = clock or SystemClock()
        self._confidence_threshold = confidence_threshold
        self._policy = SourcePolicy(sources)
        self._context = ContextCollector()
        self._dedup = Deduplicator(task_service._tasks, clock=self._clock)

    async def handle(self, event: CampusEvent) -> None:
        """M2 pipeline entry. Returns None (no QQ reply on task creation)."""
        outcome = await self._run(event)
        logger.debug("pipeline outcome kind=%s", outcome.kind)

    async def _run(self, event: CampusEvent) -> PipelineOutcome:
        # ---------------- L0 SourcePolicy ----------------
        policy = await self._policy.evaluate(event)
        if not policy.allowed:
            return PipelineOutcome(kind="l0_drop")
        source = await self._sources.get_by_identity(event.platform, event.conversation_id)
        if source is None:
            return PipelineOutcome(kind="l0_drop")

        # observe context BEFORE L1 (L1-rejected messages remain future context)
        self._context.observe(event, source_id=source.id, context_window=source.context_window)

        # ---------------- L1 Prefilter ----------------
        l1 = prefilter(event.text)
        audit: dict[str, Any] = {"l1": {"score": l1.score, "reasons": l1.reasons}}
        if not l1.passed:
            # NO Extraction row for L1-rejected chatter (privacy decision)
            return PipelineOutcome(kind="l1_drop")

        # ---------------- L2 Context ----------------
        context_lines = self._context.snapshot(event, context_window=source.context_window)

        # ---------------- L3 TaskExtractor ----------------
        try:
            provider = await self._provider_manager.get_default()
        except NoProviderConfiguredError:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error="no provider configured",
            )
            return PipelineOutcome(kind="provider_error")
        extractor = TaskExtractor(provider)
        try:
            result = await extractor.extract(
                current_text=event.text,
                context_lines=context_lines,
                message_time_iso=event.timestamp.isoformat(),
            )
        except ProviderError as e:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error=f"provider:{e.code.value}",
            )
            return PipelineOutcome(kind="provider_error")
        except ExtractionError as e:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error=f"parse:{e}",
            )
            return PipelineOutcome(kind="parse_error")

        audit["l3"] = {
            "structured_mode": result.structured_mode,
            "has_task": result.has_task,
            "confidence": result.task.confidence if result.task else None,
            "reason": result.task.reason if result.task else None,
        }
        if not result.has_task:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.SKIPPED.value,
                audit=audit, raw_result=result.raw, normalized_result=result.to_json(),
                confidence=result.task.confidence if result.task else None,
            )
            return PipelineOutcome(kind="model_said_none")

        task = result.task
        assert task is not None

        # ---------------- L4 TimeNormalizer ----------------
        deadline = None
        deadline_resolved = False
        if task.deadline_phrase:
            resolved = resolve_deadline(task.deadline_phrase, event.timestamp, self._tz)
            deadline = resolved.deadline
            deadline_resolved = resolved.deadline is not None
            audit["l4"] = {
                "phrase": task.deadline_phrase,
                "reason": resolved.reason,
                "resolved": resolved.deadline.isoformat() if resolved.deadline else None,
                "is_explicit": resolved.is_explicit,
            }
        else:
            audit["l4"] = {"phrase": None, "reason": "no_phrase"}

        # ---------------- L5/L6/L7 ----------------
        candidate = TaskCandidate(
            title=task.title,
            category=task.category,
            course=task.course,
            deadline=deadline,
            description=candidate_description(
                submission_method=task.submission_method, reason=task.reason
            ),
            confidence=task.confidence,
            dedup_key=f"{source.id}:{normalize_title(task.title)}:{deadline.isoformat() if deadline else ''}",
            source_id=source.id,
            source_message_id=event.message_id,
            source_text_reference=event.text,
            pending_confirm=(
                task.confidence < self._confidence_threshold
                or (task.deadline_phrase is not None and not deadline_resolved)
            ),
        )
        created: TaskCreationResult = await self._task_service.create_task(candidate)
        if not created.created:
            audit["l5"] = {"dedup": created.reason}
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.DUPLICATE.value,
                audit=audit, raw_result=result.raw, normalized_result=result.to_json(),
                confidence=task.confidence,
            )
            return PipelineOutcome(kind="duplicate", dedup_reason=created.reason)

        audit["l5"] = {"dedup": "new"}
        audit["l7"] = {"task_id": created.task.id, "status": created.task.status}
        audit["outcome"] = {"task_id": created.task.id, "status": created.task.status}
        await self._record_extraction(
            source_id=source.id, event=event, status=ExtractionStatus.SUCCESS.value,
            audit=audit, raw_result=result.raw, normalized_result=result.to_json(),
            confidence=task.confidence,
        )
        kind = "pending_confirm" if created.task.status == "pending_confirm" else "task_created"
        return PipelineOutcome(kind=kind, task_id=created.task.id)

    async def _record_extraction(
        self,
        *,
        source_id: int,
        event: CampusEvent,
        status: str,
        audit: dict[str, Any],
        raw_result: str | None = None,
        normalized_result: str | None = None,
        confidence: float | None = None,
        error: str | None = None,
    ) -> Extraction:
        audit.setdefault("outcome", {"status": status})
        audit["outcome"].update({"status": status})
        return await self._extractions.create(
            source_id=source_id,
            source_message_id=event.message_id,
            trace_id=event.trace_id,
            provider=None,
            model=None,
            status=status,
            confidence=confidence,
            raw_result=raw_result,
            normalized_result=normalized_result,
            audit=json.dumps(audit, ensure_ascii=False, sort_keys=True),
            error=error,
        )
