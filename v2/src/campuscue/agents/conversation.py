"""Conversation (M4 §25) — bounded IN-MEMORY thread state, turn-based.

THREAD MODEL: one Conversation per thread key (group:<id> / private:<id>).
History is stored as TURNS — each turn = [user message, (assistant
tool_calls + tool results)*, final assistant answer]. Trimming removes whole
OLD turns only, so a valid tool-call message sequence is NEVER cut in half
(an assistant tool_calls message and its tool results always stay together —
M4 §28 protocol-valid trimming).

Bound: conversation_max_messages total messages (oldest turns dropped first).
On process restart conversations disappear — that is acceptable in M4 (no
long-term Agent memory, no DB migration for chat history).

PRIVACY (M4 §26): real chat text lives ONLY in memory. Never persisted to
Git/logs/HANDOFF/SQLite. Logs carry trace ids, never message bodies.
"""

from __future__ import annotations

from campuscue.providers.models import LLMMessage


class Conversation:
    def __init__(self, max_messages: int = 20) -> None:
        if max_messages <= 0:
            raise ValueError(f"max_messages must be > 0, got {max_messages!r}")
        self._max_messages = max_messages
        self._turns: list[list[LLMMessage]] = []

    def begin_turn(self, user_message: LLMMessage) -> None:
        """Start a new turn (one user message). Trims OLD turns to the bound;
        the CURRENT turn is never trimmed (it is the live exchange)."""
        self._turns.append([user_message])
        self._trim()

    def append_to_current_turn(self, messages: list[LLMMessage]) -> None:
        """Extend the current turn (assistant tool_calls + tool results, or
        the final answer). Never creates a new turn."""
        if not self._turns:
            raise RuntimeError("no active turn; call begin_turn() first")
        self._turns[-1].extend(messages)

    def snapshot(self) -> list[LLMMessage]:
        """Flat, protocol-valid message list (system prompt added by caller)."""
        return [m for turn in self._turns for m in turn]

    @property
    def turns(self) -> list[list[LLMMessage]]:
        """Read-only turn list (ContextBudget trims whole turns by token)."""
        return self._turns

    def message_count(self) -> int:
        return sum(len(t) for t in self._turns)

    def _trim(self) -> None:
        total = self.message_count()
        while len(self._turns) > 1 and total > self._max_messages:
            total -= len(self._turns.pop(0))
