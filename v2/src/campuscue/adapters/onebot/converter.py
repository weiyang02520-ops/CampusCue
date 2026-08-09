"""Pure OneBot v11 payload -> CampusEvent conversion.

Must stay pure: no websocket, no API calls, no DB, no global mutable state.
ID factories and clocks are injectable for deterministic tests.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from campuscue.core.events import (
    CampusEvent,
    ConversationType,
    EventType,
    MessageSegment,
    SegmentType,
    new_event_id,
    new_trace_id,
)

IdFactory = Callable[[], str]
Clock = Callable[[], datetime]

# Frame classification (M1: Event Frame / Action Response Frame / other)
EVENT = "event"
ACTION_RESPONSE = "action_response"
IGNORED_META = "ignored_meta"  # meta_event / notice / request: safe ignore
UNKNOWN = "unknown"

# message post types we handle
_MESSAGE_POST_TYPES = {"message", "message_sent"}
# meta post types we deliberately do not turn into business events
_META_POST_TYPES = {"meta_event", "notice", "request"}
# OneBot message segment types we know how to convert (parse-only)
_SUPPORTED_SEGMENTS = {"text", "at", "reply", "image"}


class ConversionResult:
    __slots__ = ("kind", "event", "reason")

    def __init__(self, kind: str, event: CampusEvent | None = None, reason: str = "") -> None:
        self.kind = kind
        self.event = event
        self.reason = reason


def classify_frame(payload: Any) -> str:
    """Classify a raw WS JSON payload without any side effects."""
    if not isinstance(payload, dict):
        return UNKNOWN
    if "echo" in payload and isinstance(payload["echo"], str):
        return ACTION_RESPONSE
    post_type = payload.get("post_type")
    if post_type in _META_POST_TYPES:
        return IGNORED_META
    if post_type in _MESSAGE_POST_TYPES:
        return EVENT
    return UNKNOWN


def convert_message(payload: dict[str, Any], *, adapter_id: str, id_factory: IdFactory | None = None, clock: Clock | None = None) -> CampusEvent:
    """Convert a OneBot message payload to a CampusEvent. Raises ValidationError."""
    message_type = payload.get("message_type")
    if message_type == "group":
        conversation_type = ConversationType.GROUP
    elif message_type == "private":
        conversation_type = ConversationType.PRIVATE
    else:
        raise ValidationError(f"unsupported message_type: {message_type!r}")

    self_id = str(payload.get("self_id", ""))
    message_id = str(payload.get("message_id", ""))
    if not self_id or not message_id:
        raise ValidationError("missing self_id or message_id")

    sender = payload.get("sender") or {}
    sender_id = str(sender.get("user_id", ""))
    sender_name = str(sender.get("card") or sender.get("nickname") or "")
    if not sender_id:
        raise ValidationError("missing sender.user_id")

    # time: OneBot epoch seconds; fall back to injectable clock
    raw_time = payload.get("time")
    if isinstance(raw_time, (int, float)) and raw_time > 0:
        ts = datetime.fromtimestamp(float(raw_time), tz=timezone.utc)
    else:
        ts = (clock or datetime.now(timezone.utc))().astimezone(timezone.utc)
    ts = ts.astimezone(timezone.utc)

    segments, text = _parse_segments(payload.get("message"))
    event_type = (
        EventType.GROUP_MESSAGE if conversation_type == ConversationType.GROUP else EventType.PRIVATE_MESSAGE
    )
    return CampusEvent(
        event_id=(id_factory or new_event_id)(),
        trace_id=(id_factory or new_trace_id)(),
        platform="onebot",
        adapter_id=adapter_id,
        event_type=event_type,
        self_id=self_id,
        message_id=message_id,
        conversation_id=str(payload.get("group_id") or payload.get("user_id") or ""),
        conversation_type=conversation_type,
        sender_id=sender_id,
        sender_name=sender_name,
        timestamp=ts,
        text=text,
        segments=tuple(segments),
        group_id=str(payload["group_id"]) if conversation_type == ConversationType.GROUP and payload.get("group_id") is not None else None,
        metadata={"raw_message": str(payload.get("raw_message", ""))},
    )


def _parse_segments(raw: Any) -> tuple[list[MessageSegment], str]:
    """Parse the message array preserving order. text segments concatenate in order."""
    if isinstance(raw, str):
        raise ValidationError("non-array message format not supported (requires post-format=array)")
    if not isinstance(raw, list):
        raise ValidationError("missing message array")

    segments: list[MessageSegment] = []
    text_parts: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue  # skip malformed entries, never crash the adapter
        seg_type = item.get("type")
        data = item.get("data") or {}
        if seg_type in _SUPPORTED_SEGMENTS:
            if seg_type == "text":
                text_parts.append(str(data.get("text", "")))
            segments.append(MessageSegment(type=SegmentType(seg_type), data=dict(data)))
        else:
            segments.append(MessageSegment(type=SegmentType.UNKNOWN, data={"raw_type": str(seg_type), **dict(data)}))
    return segments, "".join(text_parts)


class ValidationError(ValueError):
    """Payload is invalid / unsupported. Caller logs at safe level, never crashes."""
