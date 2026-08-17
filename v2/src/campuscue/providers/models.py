"""Provider-neutral request/response contracts (M2, M4 tool extension).

M4 EXTENSION: Tool Calling is a provider-neutral protocol extension. Agent
business code (agents/, tools/) NEVER sees OpenAI wire JSON — only the
provider layer knows choices[0].message.tool_calls / function.arguments
string encoding / HTTP payload layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMToolSchema:
    """Provider-neutral tool declaration (M4). Serialized by the provider to
    the vendor wire format; agents/tools never see that serialization."""

    name: str
    description: str
    input_schema: dict[str, Any]  # JSON Schema for argument validation


@dataclass(frozen=True)
class LLMToolCall:
    """Provider-neutral tool invocation request (M4).

    arguments is ALREADY a parsed dict — the provider layer decodes the
    vendor wire format (JSON string) at the boundary. Malformed wire
    arguments raise ProviderError(MALFORMED_OUTPUT); no vendor JSON string
    ever reaches agent business logic.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class LLMMessage:
    role: str  # system | user | assistant | tool (M4)
    content: str | None  # None only for assistant tool-call messages (M4)
    # role=tool only (M4): which tool_call this result answers
    tool_call_id: str | None = None
    # role=assistant only (M4): provider-neutral tool calls in this message
    tool_calls: tuple[LLMToolCall, ...] = ()


@dataclass(frozen=True)
class LLMRequest:
    messages: list[LLMMessage]
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    # None = fall back to provider-configured timeout (M2a.1-B)
    timeout_s: float | None = None
    # JSON Schema for structured output (ADR-012; M2b uses this for extraction)
    response_schema: dict[str, Any] | None = None
    # provider-neutral intent; M2 default false. No vendor-specific wire field
    # is guessed (M2 §33): OpenAI-compatible endpoints differ.
    disable_thinking: bool = False
    # M4 TOOL EXTENSION: optional tool declarations. None = EXACTLY the M2
    # wire behavior (no tools/tool_choice keys sent at all) — M2 extraction
    # requests must not accidentally trigger tool mode (M4 §9).
    tools: tuple[LLMToolSchema, ...] | None = None
    # "auto" when tools present and not overridden; None = provider default
    tool_choice: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    role: str
    content: str  # "" for a tool-only response (content=null on the wire)
    usage: dict[str, int] = field(default_factory=dict)
    # raw provider payload retained in memory for Extraction audit; NEVER logged
    raw: dict[str, Any] = field(default_factory=dict)
    # M4: tool calls requested by the model (empty for a final text answer).
    # VALID RESPONSES: content=null + tool_calls non-empty, OR content=str +
    # tool_calls empty. Neither -> ProviderError(MALFORMED_OUTPUT).
    tool_calls: tuple[LLMToolCall, ...] = ()
