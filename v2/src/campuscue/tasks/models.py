"""Task extraction pipeline domain models (M2b.1)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from campuscue.storage.enums import TaskCategory

# Closed category set for the JSON Schema (must match TaskCategory values)
CATEGORY_VALUES = [c.value for c in TaskCategory]

EXTRACTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "has_task": {"type": "boolean"},
        "category": {"type": "string", "enum": CATEGORY_VALUES},
        "title": {"type": "string"},
        "course": {"type": "string"},
        "deadline_phrase": {"type": "string"},
        "submission_method": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["has_task"],
    "additionalProperties": False,
}

# Normalized extraction result (post L3 normalization)
@dataclass(frozen=True)
class ExtractedTask:
    category: str = TaskCategory.OTHER.value
    title: str = ""
    course: str | None = None
    deadline_phrase: str | None = None
    submission_method: str | None = None
    confidence: float = 0.5
    reason: str = ""


@dataclass
class ExtractionResult:
    """Provider-neutral L3 output.

    has_task=false retains confidence/reason/raw/structured_mode for
    auditability (M2b.1.1 Finding C) — WITHOUT fabricating a Task object.
    No title/course/deadline/submission_method is kept for a non-task result.
    """

    has_task: bool
    task: ExtractedTask | None = None
    raw: str = ""
    structured_mode: str = "json_schema"  # json_schema | json_fallback
    confidence: float | None = None  # model_said_none audit (has_task=false)
    reason: str = ""  # model_said_none audit reason (has_task=false)

    def to_json(self) -> str:
        import json

        data: dict[str, Any] = {"has_task": self.has_task}
        if self.task is not None:
            data.update(
                {
                    "category": self.task.category,
                    "title": self.task.title,
                    "course": self.task.course,
                    "deadline_phrase": self.task.deadline_phrase,
                    "submission_method": self.task.submission_method,
                    "confidence": self.task.confidence,
                    "reason": self.task.reason,
                }
            )
        else:
            data["confidence"] = self.confidence
            data["reason"] = self.reason
        return json.dumps(data, ensure_ascii=False)


@dataclass(frozen=True)
class PrefilterResult:
    passed: bool
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourcePolicyResult:
    allowed: bool
    reason: str = ""  # source_not_configured / source_disabled / auto_extract_disabled / unsupported_conversation_type


@dataclass(frozen=True)
class ResolvedDeadline:
    deadline: datetime | None  # timezone-aware UTC
    is_explicit: bool
    reason: str  # rule that matched, e.g. "weekday+clock"


@dataclass(frozen=True)
class DedupResult:
    is_duplicate: bool
    reason: str = ""
    dedup_key: str | None = None
    matched_task_id: int | None = None


@dataclass(frozen=True)
class TaskCandidate:
    """Validated candidate handed to TaskService (authoritative write boundary)."""

    title: str
    category: str
    course: str | None
    deadline: datetime | None  # aware UTC
    description: str | None
    confidence: float
    dedup_key: str
    source_id: int
    source_message_id: str
    source_text_reference: str
    pending_confirm: bool
