"""Task Extraction Pipeline (M2b.1 AI-first) — L0..L7 orchestration.

AI-FIRST (ADR-013): the LLM is the primary semantic judge. Local code handles
hygiene (hard drop only for certain garbage), signals (hints only, no veto),
deterministic validation, time, dedup, safety.

CampusEvent
→ L0 SourcePolicy
→ L1 MessageHygieneFilter (hard drop: empty/oversized/no-text only)
→ L1.5 LocalSignalAnalyzer (hints, never a gate)
→ L2 ContextCollector
→ L3 LLM Triage + Extraction (single call; schema fallback ≤2 calls)
→ L4 Deterministic Validation + TimeNormalizer
→ L5 Deduplicator
→ L6 Confidence / Confirmation
→ L7 TaskService → SQLite

Privacy: hygiene drops persist nothing. model_said_none persists ONE audit
Extraction (provider consumed) WITHOUT full input context. Only created Tasks
persist source_text_reference.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

from campuscue.core.events import CampusEvent
from campuscue.core.realtime import RealtimeNotifier
from campuscue.providers.errors import NoProviderConfiguredError, ProviderError
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
from campuscue.tasks.dedup import build_dedup_key
from campuscue.tasks.extractor import ExtractionError, TaskExtractor
from campuscue.tasks.models import TaskCandidate
from campuscue.tasks.prefilter import analyze_signals, hygiene_check
from campuscue.tasks.source_policy import SourcePolicy
from campuscue.tasks.time_normalizer import resolve_deadline

logger = logging.getLogger("campuscue.tasks.pipeline")

CONFIDENCE_THRESHOLD = 0.6


@dataclass
class PipelineOutcome:
    kind: str  # hygiene_drop | model_said_none | task_created | pending_confirm | duplicate | provider_error | parse_error | normalization_error
    task_id: int | None = None
    dedup_reason: str = ""


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
        notifier: RealtimeNotifier | None = None,
    ) -> None:
        self._sources = sources
        self._extractions = extractions
        self._task_service = task_service
        self._provider_manager = provider_manager
        self._tz = timezone
        self._clock = clock or SystemClock()
        self._confidence_threshold = confidence_threshold
        self._notifier = notifier
        self._policy = SourcePolicy(sources)
        self._context = ContextCollector()

    async def handle(self, event: CampusEvent) -> None:
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

        # ---------------- L1 MessageHygieneFilter (hard drop only for certain garbage) ----
        hygiene = hygiene_check(event.text)
        if not hygiene.passed:
            return PipelineOutcome(kind="hygiene_drop")

        # ---------------- L1.5 LocalSignalAnalyzer (hints, never a gate) ----
        signals = analyze_signals(event.text)
        audit: dict[str, Any] = {
            "local_signals": {
                "score": signals.score,
                "tags": signals.tags,
                "reasons": signals.reasons,
            }
        }

        # ---------------- L2 ContextCollector (observe BEFORE LLM) ----
        self._context.observe(event, source_id=source.id, context_window=source.context_window)
        context_lines = self._context.snapshot(event, context_window=source.context_window)

        # ---------------- L3 LLM Triage + Extraction (single call) ----
        try:
            provider = await self._provider_manager.get_default()
        except NoProviderConfiguredError:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error="no_provider_configured",
            )
            return PipelineOutcome(kind="provider_error")
        # safe provider/model identity for audit (no secrets; M2b.1.1 Finding B)
        provider_ident = provider.provider_type
        model_ident = provider.model
        extractor = TaskExtractor(provider)
        try:
            result = await extractor.extract(
                current_text=event.text,
                context_lines=context_lines,
                message_time_iso=event.timestamp.isoformat(),
                signal_hints=signals.tags,
            )
        except ProviderError as e:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error=f"provider:{e.code.value}",
                provider=provider_ident, model=model_ident,
            )
            return PipelineOutcome(kind="provider_error")
        except ExtractionError as e:
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.ERROR.value,
                audit=audit, error=f"parse:{e}",
                provider=provider_ident, model=model_ident,
            )
            return PipelineOutcome(kind="parse_error")

        audit["l3"] = {
            "structured_mode": result.structured_mode,
            "has_task": result.has_task,
            "confidence": result.task.confidence if result.task else result.confidence,
            "reason": result.task.reason if result.task else result.reason,
        }
        if not result.has_task:
            # model said none: one audit Extraction WITHOUT full input context
            # (only the model output + confidence + short reason; input text is
            # NOT persisted here — M2b.1.1 Finding C auditability contract)
            await self._record_extraction(
                source_id=source.id, event=event, status=ExtractionStatus.SKIPPED.value,
                audit=audit, raw_result=result.raw, normalized_result=result.to_json(),
                confidence=result.confidence,
                provider=provider_ident, model=model_ident,
            )
            return PipelineOutcome(kind="model_said_none")

        task = result.task
        assert task is not None

        # ---------------- L4 Deterministic Validation + TimeNormalizer ----
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
            dedup_key=build_dedup_key(title=task.title, course=task.course, deadline=deadline),
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
                provider=provider_ident, model=model_ident,
            )
            return PipelineOutcome(kind="duplicate", dedup_reason=created.reason)

        audit["l5"] = {"dedup": "new"}
        audit["l7"] = {"task_id": created.task.id, "status": created.task.status}
        audit["outcome"] = {"task_id": created.task.id, "status": created.task.status}
        await self._record_extraction(
            source_id=source.id, event=event, status=ExtractionStatus.SUCCESS.value,
            audit=audit, raw_result=result.raw, normalized_result=result.to_json(),
            confidence=task.confidence,
            provider=provider_ident, model=model_ident,
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
        provider: str | None = None,
        model: str | None = None,
    ) -> Extraction:
        audit.setdefault("outcome", {"status": status})
        audit["outcome"].update({"status": status})
        row = await self._extractions.create(
            source_id=source_id,
            source_message_id=event.message_id,
            trace_id=event.trace_id,
            provider=provider,
            model=model,
            status=status,
            confidence=confidence,
            raw_result=raw_result,
            normalized_result=normalized_result,
            audit=json.dumps(audit, ensure_ascii=False, sort_keys=True),
            error=error,
        )
        if self._notifier is not None:
            await self._notifier.publish(
                "extraction.updated",
                {
                    "id": row.id,
                    "source_id": row.source_id,
                    "source_message_id": row.source_message_id,
                    "status": row.status,
                    "confidence": row.confidence,
                    "created_at": row.created_at.isoformat(),
                },
            )
        return row
