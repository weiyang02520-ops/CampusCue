"""L2: one LLM call per surviving message, returning structured JSON.

Talks to the Ark endpoint over plain HTTP rather than through astrbot's
ProviderManager. The reason is not distrust of the provider layer -- it is that
this call needs two things the conversational path does not offer: the
``thinking: disabled`` switch, and a hard guarantee that no conversation history
or persona leaks into the prompt. Extraction must be a pure function of one
message, or the same notice would classify differently depending on what was
said in the group earlier.

``thinking: disabled`` is not an optimisation, it is a requirement. Measured on
the project's own endpoint (see campuscue/_ark_probe2.py):

    thinking on   4134 reasoning tokens, 76s, some calls time out entirely
    thinking off     0 reasoning tokens,  2s, identical extraction quality
"""

from __future__ import annotations

import json
import os
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx

from campuscue.extractor.prompt import SYSTEM_PROMPT, build_user_message

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_TIMEOUT = 25.0
"""Deliberately short. A student's task board is worthless if it lags the group
by a minute, and a message that times out is retried by the caller rather than
holding a slot open."""

TASK_TYPES = frozenset({"homework", "exam", "competition", "activity", "notice"})


class ExtractionError(RuntimeError):
    """The model could not be reached, or answered with something unusable."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "extraction_error",
        raw_response: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.raw_response = raw_response


@dataclass
class Extraction:
    """One parsed L2 result."""

    is_task: bool
    task_type: str | None = None
    title: str | None = None
    deadline_phrase: str | None = None
    location: str | None = None
    items: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""

    raw_response: str = ""
    """Kept verbatim. It is the only way to diagnose a malformed answer, and on
    stage it is the evidence that the JSON came from the model rather than a
    fixture."""
    model: str = ""
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def load_env_file(root: pathlib.Path | None = None) -> None:
    """Load .env into os.environ without overwriting anything already set.

    The project has no python-dotenv dependency and does not need one; this is
    twelve lines and keeps the key out of every other module.
    """
    path = (root or pathlib.Path(__file__).resolve().parents[2]) / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _as_bool(value: Any, default: bool = False) -> bool:
    """Coerce a model-provided boolean, tolerating string drift.

    ``bool("false")`` is True, so a model that emits is_task as the string
    "false" (or "no", "0") would flip the whole classification. Accept real
    booleans, numbers, and the common string spellings; anything else falls
    back to ``default``.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "是", "有")
    return default


def _coerce(payload: dict[str, Any]) -> Extraction:
    """Normalise the model's answer, tolerating the ways it drifts.

    Trusting the shape blindly is how a pipeline ends up storing the string
    "null" as a title or a confidence of 95. The model is well behaved in
    practice, but it runs thousands of times a day and only needs to drift once.
    """
    is_task = _as_bool(payload.get("is_task"))

    task_type = payload.get("task_type")
    if task_type not in TASK_TYPES:
        task_type = None

    def clean(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        # Models occasionally spell null as a word rather than emitting JSON null.
        if not value or value.lower() in {"null", "none", "n/a", "无", "未提及"}:
            return None
        return value

    items_raw = payload.get("items")
    items: list[str] = []
    if isinstance(items_raw, list):
        items = [str(i).strip() for i in items_raw if str(i).strip()]
    elif cleaned := clean(items_raw):
        items = [cleaned]

    try:
        confidence = float(payload.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    # Guard against a model that answers 95 meaning 95%.
    if confidence > 1.0:
        confidence = confidence / 100.0 if confidence <= 100.0 else 1.0
    confidence = max(0.0, min(1.0, confidence))

    if not is_task:
        # Never carry task fields on a non-task: a stray title would otherwise
        # reach the board through a later code path.
        return Extraction(
            is_task=False,
            confidence=confidence,
            reason=clean(payload.get("reason")) or "",
        )

    return Extraction(
        is_task=True,
        task_type=task_type,
        title=clean(payload.get("title")),
        deadline_phrase=clean(payload.get("deadline_phrase")),
        location=clean(payload.get("location")),
        items=items,
        confidence=confidence,
        reason=clean(payload.get("reason")) or "",
    )


def _parse_content(content: str) -> dict[str, Any]:
    """Parse the model's text as JSON, recovering from fenced or padded output."""
    text = content.strip()
    if text.startswith("```"):
        # ```json ... ``` -- strip the fence rather than failing the extraction.
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ExtractionError(
                "model output contained no JSON object",
                code="invalid_model_output",
                raw_response=content,
            )
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ExtractionError(
                "model output contained invalid JSON",
                code="invalid_model_output",
                raw_response=content,
            ) from exc
    if not isinstance(parsed, dict):
        raise ExtractionError(
            f"model returned {type(parsed).__name__}, not an object",
            code="invalid_model_shape",
            raw_response=content,
        )
    return parsed


async def extract(
    client: httpx.AsyncClient,
    *,
    text: str,
    sent_at: datetime,
    group_name: str | None = None,
    course_name: str | None = None,
    sender_name: str | None = None,
    sender_role: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Extraction:
    """Ask the model to classify and destructure one message.

    Args:
        client: Caller-owned HTTP client, so connections are pooled across the
            many extractions a busy group produces.
        text: The raw message body.
        sent_at: When the message was sent. Passed to the model as context and
            used later by L3 as the anchor for relative phrases.
        api_key: Defaults to ``$ARK_API_KEY``.
        model: Ark endpoint id. Defaults to ``$ARK_EXTRACT_MODEL``, falling back
            to ``$ARK_MODEL`` -- extraction is a fixed-format task, so it can run
            on a cheaper endpoint than conversation.

    Returns:
        A validated Extraction.

    Raises:
        ExtractionError: On transport failure, an API error, or output that
            cannot be read as a JSON object.
    """
    load_env_file()
    key = api_key or os.environ.get("ARK_API_KEY")
    endpoint = (
        model or os.environ.get("ARK_EXTRACT_MODEL") or os.environ.get("ARK_MODEL")
    )
    if not key:
        raise ExtractionError("ARK_API_KEY is not set", code="missing_api_key")
    if not endpoint:
        raise ExtractionError(
            "ARK_EXTRACT_MODEL / ARK_MODEL is not set", code="missing_model"
        )

    payload = {
        "model": endpoint,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": build_user_message(
                    text=text,
                    sent_at=sent_at,
                    group_name=group_name,
                    course_name=course_name,
                    sender_name=sender_name,
                    sender_role=sender_role,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 800,
        # See the module docstring: without this the endpoint spends thousands of
        # reasoning tokens and tens of seconds on a classification.
        "thinking": {"type": "disabled"},
    }

    started = time.perf_counter()
    try:
        response = await client.post(
            f"{ARK_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ExtractionError(
            f"request to Ark failed: {exc!r}", code="transport_error"
        ) from exc

    latency_ms = int((time.perf_counter() - started) * 1000)

    try:
        body = response.json()
    except ValueError as exc:
        raise ExtractionError(
            f"Ark returned non-JSON (HTTP {response.status_code})",
            code="non_json_response",
        ) from exc

    if error := body.get("error"):
        raise ExtractionError(
            f"Ark error {error.get('code')}: {error.get('message', '')[:200]}",
            code="ark_error",
        )
    if response.status_code >= 400:
        raise ExtractionError(
            f"Ark returned HTTP {response.status_code}", code="http_error"
        )

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExtractionError(
            "Ark response had no message content", code="missing_content"
        ) from exc

    result = _coerce(_parse_content(content))
    result.raw_response = content
    result.model = body.get("model") or endpoint
    result.latency_ms = latency_ms
    usage = body.get("usage") or {}
    result.prompt_tokens = usage.get("prompt_tokens")
    result.completion_tokens = usage.get("completion_tokens")
    return result


__all__ = ["Extraction", "ExtractionError", "extract", "load_env_file"]
