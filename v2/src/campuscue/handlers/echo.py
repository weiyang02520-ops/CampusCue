"""EchoHandler - the only M1 business handler.

Responds ONLY to an explicit test trigger: trimmed text == "hello".
It never echoes arbitrary group traffic (anti-repeater requirement).
"""

from __future__ import annotations

from campuscue.core.events import CampusEvent
from campuscue.core.outbound import OutgoingMessage
from campuscue.core.router import RouterResult

TRIGGER = "hello"
REPLY = "received: hello"


async def echo_handler(event: CampusEvent) -> RouterResult:
    if event.text.strip() != TRIGGER:
        return None
    return OutgoingMessage(
        conversation_id=event.conversation_id,
        conversation_type=event.conversation_type,
        text=REPLY,
    )
