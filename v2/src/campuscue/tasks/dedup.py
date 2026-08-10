"""L5 Deduplicator (M2b.1) — source-scoped, 36h window, explainable.

Priority (strongest first):
1. same source_id + source_message_id -> duplicate (strongest)
2. same source + normalized title + course + deadline-minute
3. same source + normalized title + deadline-minute (course absent)

Dismissed and done tasks remain historical evidence within the window.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from campuscue.repositories.repositories import TaskRepository
from campuscue.storage.clock import Clock, SystemClock
from campuscue.tasks.models import DedupResult

DEDUP_WINDOW = timedelta(hours=36)

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[，。！？、；：,.!?;:（）()【】\[\]「」“”\"'《》<>~～·\-—_]")


def normalize_title(title: str) -> str:
    """Case-fold, collapse whitespace, strip punctuation. Keeps Chinese
    characters and numbers (meaningful)."""
    t = _WS_RE.sub("", title.strip())
    t = _PUNCT_RE.sub("", t)
    return t.casefold()


def build_dedup_key(*, title: str, course: str | None, deadline: datetime | None) -> str:
    """CANONICAL semantic dedup key (M2b.1.1 Finding 15).

    ONE helper defines the STORED Task.dedup_key semantics, consistent with
    the Deduplicator's matching rules (same normalized title + deadline minute;
    course participates when both are known):
    - normalized title
    - course when present (both-known comparison)
    - deadline MINUTE precision (matches Deduplicator's same_minute check)

    Source scope stays separate via source_id. NO fuzzy matching.
    """
    parts = [normalize_title(title), course or ""]
    if deadline is not None:
        minute = deadline.astimezone(timezone.utc).replace(second=0, microsecond=0)
        parts.append(minute.isoformat())
    else:
        parts.append("")
    return ":".join(parts)


class Deduplicator:
    def __init__(self, tasks: TaskRepository, clock: Clock | None = None) -> None:
        self._tasks = tasks
        self._clock = clock or SystemClock()

    async def check(
        self,
        *,
        source_id: int,
        source_message_id: str,
        title: str,
        course: str | None,
        deadline: datetime | None,
    ) -> DedupResult:
        # 1) strongest: same source message
        existing = await self._tasks.find_by_source_message(source_id, source_message_id)
        if existing is not None:
            return DedupResult(
                is_duplicate=True,
                reason="same_source_message",
                dedup_key=None,
                matched_task_id=existing.id,
            )
        # 2/3) semantic: same source + normalized title (+ course) + deadline-minute
        now = self._clock.utcnow()
        if now.tzinfo is None:
            raise ValueError("clock.utcnow() must be timezone-aware")
        cutoff = now - DEDUP_WINDOW
        candidates = await self._tasks.find_recent_for_source(
            source_id=source_id, cutoff=cutoff, limit=100
        )
        norm_title = normalize_title(title)
        for t in candidates:
            if normalize_title(t.title) != norm_title:
                continue
            if t.deadline is None or deadline is None:
                if t.deadline is None and deadline is None:
                    return DedupResult(
                        is_duplicate=True, reason="same_title_no_deadline",
                        dedup_key=None, matched_task_id=t.id,
                    )
                continue
            same_minute = t.deadline.replace(second=0, microsecond=0) == deadline.replace(second=0, microsecond=0)
            if same_minute and (t.course == course or course is None or t.course is None):
                return DedupResult(
                    is_duplicate=True, reason="same_semantic_task",
                    dedup_key=None, matched_task_id=t.id,
                )
        return DedupResult(is_duplicate=False)
