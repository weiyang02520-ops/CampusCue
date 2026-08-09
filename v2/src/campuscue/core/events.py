"""CampusEvent - the unified, platform-neutral event crossing the Adapter boundary.

OneBot raw JSON never escapes the Adapter (ADR-001). Business layers only see
CampusEvent. All IDs are strings; timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ConversationType(str, Enum):
    GROUP = "group"
    PRIVATE = "private"


class EventType(str, Enum):
    GROUP_MESSAGE = "group_message"
    PRIVATE_MESSAGE = "private_message"
    SYSTEM = "system"


class SegmentType(str, Enum):
    TEXT = "text"
    AT = "at"
    REPLY = "reply"
    IMAGE = "image"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MessageSegment:
    """Ordered message segment (M1: parse-only, no external lookups)."""

    type: SegmentType
    data: dict[str, Any] = field(default_factory=dict)


def new_event_id() -> str:
    return uuid.uuid4().hex


def new_trace_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CampusEvent:
    event_id: str
    trace_id: str
    platform: str
    adapter_id: str
    event_type: EventType
    self_id: str
    message_id: str
    conversation_id: str
    conversation_type: ConversationType
    sender_id: str
    sender_name: str
    timestamp: datetime  # timezone-aware UTC
    text: str
    segments: tuple[MessageSegment, ...] = ()
    group_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_message(self) -> bool:
        return self.event_type in (EventType.GROUP_MESSAGE, EventType.PRIVATE_MESSAGE)
