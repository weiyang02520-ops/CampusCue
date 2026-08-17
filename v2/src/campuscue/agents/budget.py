"""ContextBudget (M4 §27-28) — deterministic conservative token budgeting.

- estimate, NOT an exact tokenizer (no heavy dependency for M4). Deterministic
  and deliberately conservative: CJK ~1 token/char, ASCII ~4 chars/token, so
  chars//2 + overhead never UNDERestimates for typical mixed text.
- Budget: system + conversation + tool results + current input + reserved
  output must stay below the provider's configured max_context_tokens.
- Trimming: keep the current turn (user input + its live tool chain — the
  conversation turn model guarantees protocol validity, never half a tool
  exchange); drop oldest turns first.
- If even the minimum context cannot fit -> overflow=True, the Agent stops
  gracefully with a safe context-overflow response (never a crashed request).
"""

from __future__ import annotations

from typing import Any

from campuscue.agents.conversation import Conversation
from campuscue.providers.models import LLMMessage

DEFAULT_MAX_CONTEXT_TOKENS = 4096
DEFAULT_RESERVE_OUTPUT_TOKENS = 512
_MESSAGE_OVERHEAD_TOKENS = 8  # role + structural overhead per message


def estimate_tokens(text: str | None) -> int:
    """Return a deterministic conservative estimate without a tokenizer.

    CJK ideographs and syllabaries are counted as roughly one token each;
    ASCII-like text is estimated at four non-whitespace characters per token.
    A small fixed margin protects punctuation and provider chat framing.
    """
    if not text:
        return 0
    cjk = 0
    other = 0
    for char in text:
        if char.isspace():
            continue
        codepoint = ord(char)
        if (
            0x3400 <= codepoint <= 0x4DBF
            or 0x4E00 <= codepoint <= 0x9FFF
            or 0xF900 <= codepoint <= 0xFAFF
            or 0x3040 <= codepoint <= 0x30FF
            or 0xAC00 <= codepoint <= 0xD7AF
        ):
            cjk += 1
        else:
            other += 1
    return max(1, cjk + (other + 3) // 4) + 2


def _message_tokens(m: LLMMessage) -> int:
    total = _MESSAGE_OVERHEAD_TOKENS + estimate_tokens(m.content)
    for c in m.tool_calls:
        total += estimate_tokens(c.name)
        total += estimate_tokens(str(c.arguments))
    return total


def _turn_tokens(turn: list[LLMMessage]) -> int:
    return sum(_message_tokens(m) for m in turn)


class ContextBudget:
    def __init__(
        self,
        *,
        reserve_output_tokens: int = DEFAULT_RESERVE_OUTPUT_TOKENS,
        max_context_tokens: int | None = None,
    ) -> None:
        if reserve_output_tokens <= 0:
            raise ValueError(f"reserve_output_tokens must be > 0, got {reserve_output_tokens!r}")
        self._reserve = reserve_output_tokens
        self._max_context = max_context_tokens or DEFAULT_MAX_CONTEXT_TOKENS

    @property
    def reserve_output_tokens(self) -> int:
        return self._reserve

    def message_tokens(self, messages: list[LLMMessage]) -> int:
        return sum(_message_tokens(m) for m in messages)

    def plan(
        self,
        *,
        conversation: Conversation,
        system_prompt: str,
        current_user_text: str,
        tools_tokens: int = 0,
    ) -> tuple[list[LLMMessage], bool]:
        """Select the messages for the next provider call.

        Returns (messages, overflow). overflow=True means even the minimum
        context (system + current user + reserve) does not fit — the caller
        must stop gracefully. messages is [] in that case.
        """
        system_tokens = estimate_tokens(system_prompt)
        user_tokens = estimate_tokens(current_user_text)
        fixed = self._reserve + system_tokens + user_tokens + tools_tokens
        available = self._max_context - fixed
        if available <= 0:
            return [], True

        turns = conversation.turns  # turn model is internal by design
        # always keep the current (last) turn — live exchange
        keep: list[list[LLMMessage]] = [turns[-1]] if turns else []
        running = _turn_tokens(keep[0]) if keep else 0
        if running > available:
            return [], True
        # oldest first — drop whole turns until it fits
        for turn in reversed(turns[:-1]):
            t = _turn_tokens(turn)
            if running + t > available:
                break
            keep.insert(0, turn)
            running += t
        return [m for turn in keep for m in turn], False
