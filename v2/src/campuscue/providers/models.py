"""Provider-neutral request/response contracts (M2).

M2 request MUST NOT depend on ToolSet/ToolRegistry/ToolDefinition/AgentRuntime
(M4 extends the contract later).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    timeout_s: float = 30.0
    # JSON Schema for structured output (ADR-012; M2b uses this for extraction)
    response_schema: dict[str, Any] | None = None
    # provider-neutral intent; M2 default false. No vendor-specific wire field
    # is guessed (M2 §33): OpenAI-compatible endpoints differ.
    disable_thinking: bool = False


@dataclass(frozen=True)
class LLMResponse:
    role: str
    content: str
    usage: dict[str, int] = field(default_factory=dict)
    # raw provider payload retained in memory for Extraction audit; NEVER logged
    raw: dict[str, Any] = field(default_factory=dict)
    # tool_calls: M4 EXTENSION — inactive in M2, no parsing implemented
