"""L3 TaskExtractor (M2b.1).

Provider-neutral extraction through the M2a Provider abstraction. Business
code never builds HTTP JSON. JSON Schema preferred; documented fallback to a
strict JSON-only prompt + tolerant parser ONLY on ProviderError INVALID_REQUEST
(retry once). AUTH/TIMEOUT/NETWORK/RATE_LIMIT/etc are real failures — no fallback.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.models import LLMMessage, LLMRequest
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.tasks.models import EXTRACTION_JSON_SCHEMA, ExtractedTask, ExtractionResult
from campuscue.tasks.prompts import FALLBACK_PROMPT, build_system_prompt, build_user_message

logger = logging.getLogger("campuscue.tasks.extractor")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


class ExtractionError(Exception):
    """Safe, classified extraction failure (parse/shape/normalization)."""


class TaskExtractor:
    def __init__(self, provider: OpenAICompatibleProvider) -> None:
        self._provider = provider

    async def extract(
        self,
        *,
        current_text: str,
        context_lines: list[str],
        message_time_iso: str,
    ) -> ExtractionResult:
        user_msg = build_user_message(
            current_text=current_text, context_lines=context_lines, message_time=message_time_iso
        )
        base_request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=build_system_prompt()),
                LLMMessage(role="user", content=user_msg),
            ],
            model=self._provider._model,
            response_schema=EXTRACTION_JSON_SCHEMA,
        )
        # Attempt 1: JSON Schema structured output
        try:
            resp = await self._provider.chat(base_request)
            return self._parse_and_normalize(resp.content, structured_mode="json_schema")
        except ProviderError as e:
            if e.code != ProviderErrorCode.INVALID_REQUEST:
                raise  # real failure: no fallback
        # Attempt 2 (ONCE): fallback strict JSON-only prompt (endpoint rejected schema)
        fallback_request = LLMRequest(
            messages=[
                LLMMessage(role="system", content="你是校园事务提取器。只输出一个 JSON 对象。"),
                LLMMessage(role="user", content=FALLBACK_PROMPT.format(message=user_msg)),
            ],
            model=self._provider._model,
        )
        resp = await self._provider.chat(fallback_request)
        return self._parse_and_normalize(resp.content, structured_mode="json_fallback")

    def _parse_and_normalize(self, content: str, *, structured_mode: str) -> ExtractionResult:
        data = parse_json_object(content)
        normalized = normalize_extraction(data)
        if not normalized["has_task"]:
            return ExtractionResult(has_task=False, raw=content, structured_mode=structured_mode)
        title = normalized.get("title")
        if not title or not title.strip():
            raise ExtractionError("model returned has_task=true but missing title")
        task = ExtractedTask(
            category=normalized.get("category") or "other",
            title=title.strip(),
            course=_null_or_str(normalized.get("course")),
            deadline_phrase=_null_or_str(normalized.get("deadline_phrase")),
            submission_method=_null_or_str(normalized.get("submission_method")),
            confidence=float(normalized.get("confidence") or 0.5),
            reason=str(normalized.get("reason") or ""),
        )
        return ExtractionResult(has_task=True, task=task, raw=content, structured_mode=structured_mode)


def parse_json_object(text: str) -> dict[str, Any]:
    """Tolerant JSON parse. Handles plain JSON, fenced JSON, and leading/trailing
    model prose when exactly one valid JSON object can be isolated. Never eval."""
    text = text.strip()
    if not text:
        raise ExtractionError("empty model output")
    # 1) plain JSON
    try:
        data = json.loads(text)
        return _require_object(data)
    except (json.JSONDecodeError, ExtractionError):
        pass
    # 2) fenced JSON
    m = _FENCE_RE.search(text)
    if m:
        try:
            data = json.loads(m.group(1).strip())
            return _require_object(data)
        except (json.JSONDecodeError, ExtractionError):
            pass
    # 3) isolate first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            return _require_object(data)
        except (json.JSONDecodeError, ExtractionError):
            pass
    raise ExtractionError("no valid JSON object found in model output")


def _require_object(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ExtractionError(f"expected JSON object, got {type(data).__name__}")
    return data


def _null_or_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if v in ("", "null", "none", "无", "暂无"):
            return None
        return v
    return str(value)


def normalize_extraction(data: dict[str, Any]) -> dict[str, Any]:
    """Defensive normalization of model drift. Never raises on bad values except
    structural impossibility."""
    has_task = _as_bool(data.get("has_task", False))
    normalized: dict[str, Any] = {"has_task": has_task}
    if not has_task:
        return normalized

    category = str(data.get("category") or "other").strip().lower()
    from campuscue.storage.enums import TaskCategory

    valid = {c.value for c in TaskCategory}
    normalized["category"] = category if category in valid else "other"

    normalized["title"] = str(data.get("title") or "").strip()
    normalized["course"] = _null_or_str(data.get("course"))
    normalized["deadline_phrase"] = _null_or_str(data.get("deadline_phrase"))
    normalized["submission_method"] = _null_or_str(data.get("submission_method"))

    confidence = _coerce_confidence(data.get("confidence"))
    normalized["confidence"] = confidence
    normalized["reason"] = str(data.get("reason") or "")
    return normalized


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "1", "是", "有"):
            return True
        if v in ("false", "no", "0", "否", "无", "null", "none"):
            return False
    return bool(value)


def _coerce_confidence(value: Any) -> float:
    """95 -> 0.95; clamp to 0..1; string drift tolerated."""
    if value is None:
        return 0.5
    try:
        v = float(str(value).strip())
    except (TypeError, ValueError):
        return 0.5
    if v > 1.0 and v <= 100.0:
        v = v / 100.0
    return max(0.0, min(1.0, v))
