"""L2 ContextCollector (M2b.1) — bounded EPHEMERAL per-source ring buffer.

No messages table. Restart loses context (accepted by ADR-012). Only
message_id/timestamp/text are stored. L1-rejected messages are still observed
(after L0 pass) because they may disambiguate a later candidate; they are never
sent to the LLM unless a later candidate needs context.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from campuscue.core.events import CampusEvent


@dataclass(frozen=True)
class ContextMessage:
    message_id: str
    timestamp: datetime  # aware UTC
    text: str


class ContextCollector:
    def __init__(self) -> None:
        # source identity (platform, conversation_id) -> deque of ContextMessage
        self._buffers: dict[tuple[str, str], deque[ContextMessage]] = {}

    def _buffer_for(self, key: tuple[str, str], *, context_window: int) -> deque[ContextMessage]:
        """Get-or-create the source buffer, RESIZING when the configured
        context_window changed since the buffer was created (M2b.1.1 Finding E).

        deque.maxlen is fixed at construction; a stale maxlen would silently
        cap/slice the ring at the old window. Preserve as many currently
        retained messages as possible when resizing (older discarded messages
        cannot be recovered — acceptable). Shrink safely too.
        """
        window = max(context_window, 1)
        buf = self._buffers.get(key)
        if buf is None:
            buf = deque(maxlen=window)
            self._buffers[key] = buf
            return buf
        if buf.maxlen != window:
            resized = deque(buf, maxlen=window)
            self._buffers[key] = resized
            return resized
        return buf

    def observe(self, event: CampusEvent, *, source_id: int, context_window: int) -> None:
        """Append current message to the source buffer (after L0 pass)."""
        key = (event.platform, event.conversation_id)
        buf = self._buffer_for(key, context_window=context_window)
        buf.append(
            ContextMessage(
                message_id=event.message_id,
                timestamp=event.timestamp,
                text=event.text,
            )
        )

    def snapshot(self, event: CampusEvent, *, context_window: int) -> list[str]:
        """Previous messages for the source, EXCLUDING the current one, honoring
        the CURRENT configured context_window bound (resize-safe)."""
        key = (event.platform, event.conversation_id)
        buf = self._buffers.get(key)
        if buf is None:
            return []
        # exclude current message_id (must appear exactly once in LLM input)
        previous = [m for m in buf if m.message_id != event.message_id]
        return [m.text for m in previous[-context_window:]] if context_window > 0 else []
