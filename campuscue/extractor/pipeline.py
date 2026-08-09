"""Orchestration: one message in, at most one task out.

Every path through this function ends in either a stored task, a stored audit
row explaining why there is no task, or an L1 rejection counted in aggregate.
Nothing is silently dropped -- the trace panel in the UI is only honest if the
pipeline actually records its own decisions, including the negative ones.

The function never raises. It runs from a background task spawned per group
message, and a message the pipeline cannot handle must not take down the
observer for every message after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from astrbot.core import logger
from campuscue import store
from campuscue.extractor.llm import Extraction, ExtractionError, extract
from campuscue.extractor.prefilter import prefilter
from campuscue.extractor.timeresolve import resolve_deadline
from campuscue.models import CampusExtraction, CampusTask


@dataclass
class MessageContext:
    """Everything the pipeline needs to know about one incoming message."""

    umo: str
    """Where the message came from, and where a reminder would be pushed."""
    text: str
    sent_at: datetime
    message_id: str | None = None
    sender_id: str | None = None
    sender_name: str | None = None
    sender_role: str | None = None
    """The platform's own role for this sender -- ``owner`` / ``admin`` /
    ``member`` on OneBot. Group owners and admins are treated as authoritative
    without anyone configuring ``authority_senders`` by hand, because in a real
    course group that is exactly who the teacher and the monitor are."""
    is_authority: bool = False
    """True when the sender is authoritative on this origin (owner/admin role,
    or listed in the source's authority_senders). Kept separate from the raw
    role so replay can stage a teacher without a live platform role."""
    group_name: str | None = None
    source_kind: str = "extracted"
    """extracted for live traffic, replay for the demo script -- so a
    presentation can prove which path produced a task."""


AUTHORITY_ROLES = {
    "owner": "群主（多为任课教师/辅导员）",
    "admin": "群管理员（多为班委）",
}
"""Platform roles that count as authoritative on their own. Kept small on
purpose: ``member`` must never be in here or every classmate becomes a teacher
and L1's threshold stops meaning anything."""


def _authority_label(role: str | None) -> str | None:
    return AUTHORITY_ROLES.get((role or "").strip().lower())


@dataclass
class PipelineOutcome:
    """What happened, for logging and for the replay script's console output."""

    outcome: str
    task: CampusTask | None = None
    extraction: Extraction | None = None
    detail: str = ""


async def process_message(
    ctx: MessageContext,
    *,
    client: httpx.AsyncClient,
) -> PipelineOutcome:
    """Run L1 -> L2 -> L3 for one message and persist the result."""
    try:
        return await _process(ctx, client=client)
    except Exception as exc:  # noqa: BLE001 - see module docstring
        logger.exception(
            "[campuscue] pipeline crashed (message_id=%s, chars=%d)",
            ctx.message_id,
            len(ctx.text),
        )
        return PipelineOutcome("pipeline_error", detail=repr(exc))


async def _process(
    ctx: MessageContext, *, client: httpx.AsyncClient
) -> PipelineOutcome:
    profile = None
    source = None

    # --- L1 -------------------------------------------------------------
    async with store.db_helper.get_db() as session:
        source = await store.get_or_create_source(session, ctx.umo)
        authority = list(source.authority_senders or [])
        course_name = source.course_name
        group_name = ctx.group_name or source.display_name
        enabled = source.enabled

    if not enabled:
        return PipelineOutcome("source_disabled")

    # Two ways to be authoritative: configured by hand on the source, or holding
    # owner/admin in the group itself (or explicitly staged by the caller, e.g.
    # replay). The second one is what makes terse teacher messages ("完成第35页
    # 到第40页") reach the model without any setup.
    role_label = _authority_label(ctx.sender_role)
    is_authority = (
        ctx.is_authority
        or bool(ctx.sender_id and ctx.sender_id in authority)
        or bool(role_label)
    )
    sender_role_hint = role_label or ("任课教师" if is_authority else None)
    l1 = prefilter(ctx.text, is_authority_sender=is_authority)

    if not l1.passed:
        # No audit row on purpose -- an active group would produce tens of
        # thousands a day and the useful signal is all post-L1. The counters keep
        # the filter ratio measurable.
        await store.bump_source_stats(ctx.umo, seen=1)
        logger.debug(
            "[campuscue] L1 rejected (%s, score=%.1f, chars=%d)",
            l1.reject_reason,
            l1.score,
            len(ctx.text),
        )
        return PipelineOutcome("l1_rejected", detail=l1.reject_reason or "")

    await store.bump_source_stats(ctx.umo, seen=1, l1_passed=1)

    audit = CampusExtraction(
        umo=ctx.umo,
        source_message_id=ctx.message_id,
        raw_text=ctx.text,
        message_sent_at=ctx.sent_at,
        l1_score=l1.score,
        l1_hits=l1.as_hits_json(),
        outcome="llm_error",  # replaced below; a crash mid-flight stays honest
    )

    # --- L2 -------------------------------------------------------------
    try:
        result = await extract(
            client,
            text=ctx.text,
            sent_at=ctx.sent_at,
            group_name=group_name,
            course_name=course_name,
            sender_name=ctx.sender_name,
            sender_role=sender_role_hint,
        )
    except ExtractionError as exc:
        audit.outcome = "llm_error"
        audit.error = str(exc)
        audit.l2_raw_response = exc.raw_response
        await store.record_extraction(audit)
        logger.warning("[campuscue] L2 failed (%s)", exc.code)
        return PipelineOutcome("llm_error", detail=str(exc))

    audit.l2_model = result.model
    audit.l2_raw_response = result.raw_response
    audit.l2_latency_ms = result.latency_ms
    audit.l2_prompt_tokens = result.prompt_tokens
    audit.l2_completion_tokens = result.completion_tokens
    audit.l2_parsed = {
        "is_task": result.is_task,
        "task_type": result.task_type,
        "title": result.title,
        "deadline_phrase": result.deadline_phrase,
        "location": result.location,
        "items": result.items,
        "confidence": result.confidence,
        "reason": result.reason,
    }

    if not result.is_task or not result.title:
        audit.outcome = "model_said_none"
        await store.record_extraction(audit)
        return PipelineOutcome("model_said_none", extraction=result)

    # --- L3 -------------------------------------------------------------
    resolved = resolve_deadline(result.deadline_phrase or "", ctx.sent_at)
    audit.l3_resolved_deadline = resolved.at
    audit.l3_notes = {
        "phrase": resolved.phrase,
        "basis": resolved.basis,
        "is_explicit": resolved.is_explicit,
        "note": resolved.note,
    }

    if result.deadline_phrase and resolved.at is None:
        # The model found a time expression but code could not resolve it, or
        # resolved it to something impossible. Guessing here is how a task ends
        # up with a plausible-looking wrong date, so the task is kept without a
        # deadline and flagged for confirmation instead.
        logger.info(
            "[campuscue] unresolved deadline (%s, message_id=%s)",
            resolved.note or resolved.basis,
            ctx.message_id,
        )

    async with store.db_helper.get_db() as session:
        profile = await store.get_or_create_profile(session, ctx.umo)
        threshold = profile.confidence_threshold
        auto_confirm = profile.auto_confirm

    key = store.dedup_key(ctx.umo, result.title, resolved.at)

    async with store.db_helper.get_db() as session:
        existing = await store.find_duplicate(session, umo=ctx.umo, key=key)
    if existing is not None:
        audit.outcome = "duplicate"
        audit.task_id = existing.task_id
        await store.record_extraction(audit)
        logger.debug("[campuscue] duplicate of task %s", existing.task_id)
        return PipelineOutcome("duplicate", task=existing, extraction=result)

    # A task the code could not date is never live: an unresolvable deadline is
    # exactly the case a human should look at.
    needs_confirm = (
        result.confidence < threshold
        or (result.deadline_phrase and resolved.at is None)
        or resolved.at is None
    )
    status = "active" if (auto_confirm or not needs_confirm) else "pending_confirm"

    task = CampusTask(
        umo=ctx.umo,
        title=result.title,
        task_type=result.task_type or "notice",
        status=status,
        deadline=resolved.at,
        deadline_is_explicit=resolved.is_explicit,
        location=result.location,
        items=result.items,
        confidence=result.confidence,
        source_kind=ctx.source_kind,
        source_umo=ctx.umo,
        source_group_name=group_name,
        source_sender_name=ctx.sender_name,
        source_message_id=ctx.message_id,
        source_sent_at=ctx.sent_at,
        raw_text=ctx.text,
        extract_reason=result.reason,
        dedup_key=key,
    )
    task = await store.create_task(task)

    audit.outcome = "task_created" if status == "active" else "pending_confirm"
    audit.task_id = task.task_id
    await store.record_extraction(audit)
    await store.bump_source_stats(ctx.umo, tasks_created=1)

    # Announce it now, not at the deadline. This is the moment the product's claim
    # becomes observable: the teacher typed, and seconds later the student's own
    # chat and desktop say so. Failures are reported, never raised -- the task is
    # the product, the notification is the courtesy.
    try:
        from campuscue import notify

        delivery = await notify.announce_detection(task)
        if delivery.skipped:
            logger.debug("[campuscue] detection notice skipped: %s", delivery.skipped)
    except Exception:  # noqa: BLE001
        logger.exception("[campuscue] could not announce task %s", task.task_id)

    # Schedule the reminders. This is the step that makes the product proactive
    # rather than an auto-filled list, so it runs even for pending_confirm tasks:
    # a task waiting on confirmation still has a real deadline, and going quiet
    # until someone notices the confirmation queue defeats the point.
    # Failures are logged and swallowed -- an unreminded task on the board beats
    # losing the extraction.
    try:
        from campuscue import reminders

        planned = await reminders.schedule_for_task(task)
        if planned:
            task = await store.get_task(task.task_id) or task
    except Exception:  # noqa: BLE001
        logger.exception(
            "[campuscue] could not schedule reminders for task %s", task.task_id
        )

    # Push to any open board. Imported here to keep the pipeline usable without
    # the HTTP layer (the replay script and the tests do exactly that).
    try:
        from campuscue.api.events import hub
        from campuscue.api.schemas import TaskOut

        hub.publish(
            "task_created" if status == "active" else "task_pending",
            TaskOut.of(task).model_dump(mode="json"),
        )
    except Exception:  # noqa: BLE001 - the board is a nicety, the task is the product
        logger.debug("[campuscue] could not publish task event", exc_info=True)

    logger.info(
        "[campuscue] %s task=%s (%dms)",
        audit.outcome,
        task.task_id,
        result.latency_ms,
    )
    return PipelineOutcome(audit.outcome, task=task, extraction=result)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


__all__ = ["MessageContext", "PipelineOutcome", "process_message", "utcnow"]
