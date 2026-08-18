"""AgentContext (M4 §24) — trusted context for one agent turn.

Built by CampusAgentRuntime from the real CampusEvent + source lookup, never
from model input. Holds the thread key, the source scope, the current user
message/event timestamp/timezone — NOT a 30-field framework object.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from campuscue.core.events import ConversationType


def thread_key(platform: str, conversation_type: ConversationType, conversation_id: str) -> str:
    """Bounded in-memory thread identity (M4 §25): group:<id> / private:<id>
    with platform prefix so different adapters never collide. Never logged raw
    (logs carry only a short trace reference)."""
    return f"{platform}:{conversation_type.value}:{conversation_id}"


@dataclass(frozen=True)
class AgentContext:
    platform: str
    # trusted source scope (None when DB has no source row for this conversation)
    source_id: int | None
    conversation_id: str
    conversation_type: ConversationType
    message_id: str
    timestamp: datetime  # timezone-aware UTC (current event time)
    trace_id: str
    timezone: ZoneInfo
    user_text: str = ""  # trusted current user message; never tool-controlled

    @property
    def thread(self) -> str:
        return thread_key(self.platform, self.conversation_type, self.conversation_id)
