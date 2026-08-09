"""OutgoingMessage - platform-neutral outbound unit.

Business layers never construct OneBot action JSON (ADR-001). The Adapter maps
conversation_type -> OneBot action.
"""

from __future__ import annotations

from dataclasses import dataclass

from campuscue.core.events import ConversationType


@dataclass(frozen=True)
class OutgoingMessage:
    conversation_id: str
    conversation_type: ConversationType
    text: str
