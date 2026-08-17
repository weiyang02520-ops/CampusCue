"""ToolContext (M4 §13) — trusted execution context owned by CampusCue.

SECURITY BOUNDARY: the MODEL MUST NOT provide source_id / conversation_id /
group id / user id / permission scope inside tool arguments. Tools read these
facts ONLY from ToolContext, which CampusAgentRuntime builds from the real
CampusEvent + source lookup. Tool JSON Schemas do not accept those fields at
all (additionalProperties=False); execution ignores any stray arguments.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from campuscue.core.events import ConversationType


@dataclass(frozen=True)
class ToolContext:
    platform: str
    # int | None when the DB has no source row for this conversation
    source_id: int | None
    conversation_id: str
    conversation_type: ConversationType
    message_id: str
    timestamp: datetime  # timezone-aware UTC (current event time)
    trace_id: str
    timezone: ZoneInfo
