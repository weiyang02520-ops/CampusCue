"""ToolRegistry (M4 §10-13) — provider-neutral tool registration + safe execution.

- ToolDefinition: name/description/input_schema(JSON Schema)/permission + execute
- ToolResult: ok/content/data/error (sanitized; no Python tracebacks to model)
- ToolRegistry:
    register   duplicate name -> fail fast (ValueError)
    get/list   discovery
    provider_schemas -> provider-neutral LLMToolSchema list (M4 §6: agents
                       never produce OpenAI wire JSON)
    execute    jsonschema validation BEFORE implementation; asyncio timeout
               bound; unknown tool -> safe failure ToolResult (no crash)

EXECUTION CONTEXT (M4 §13): execute() receives the trusted ToolContext; the
model NEVER supplies source scope inside arguments (JSON Schemas reject those
fields; scope comes from CampusCue runtime context).
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from campuscue.providers.models import LLMToolSchema
from campuscue.tools.context import ToolContext

# OpenAI-compatible function-name constraint (provider protocol level)
_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

# Default execution bound per tool call (configurable at the registry level).
DEFAULT_TOOL_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class ToolResult:
    """Outcome of one tool execution, safe to feed back to the model.

    ok=False errors are user-safe strings (timeout / validation / sanitized
    exception). NEVER a raw Python traceback (M4 §11/§12).
    """

    ok: bool
    content: str
    data: dict[str, Any] | None = None
    error: str | None = None


class ToolDefinition(ABC):
    """Base class for a registered tool. Subclasses set class-level identity."""

    name: str = ""
    description: str = ""
    input_schema: dict[str, Any] = {}
    permission: str = "task"
    # M7.3 semantic metadata.  The registry, not scattered tool-name checks,
    # is the source of truth for the Agent confirmation boundary.
    mutation: bool = False
    requires_confirmation: bool = False
    activity_label: str = "已执行工具操作"

    @abstractmethod
    async def execute(self, *, context: ToolContext, **kwargs: Any) -> ToolResult:
        """Run the tool with validated arguments + trusted execution context."""


def _validate_tool_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError(
            f"invalid tool name {name!r}: must match ^[a-zA-Z0-9_-]{{1,64}}$"
        )


def canonical_call_identity(name: str, arguments: dict[str, Any]) -> str:
    """Deterministic identity for duplicate tool-call defense (M4 §32).

    Name + canonicalized arguments; provider-generated tool_call_id is
    deliberately excluded (IDs may change for semantically identical calls).
    """
    return f"{name}:{json.dumps(arguments, sort_keys=True, ensure_ascii=False)}"


class ToolRegistry:
    def __init__(self, *, default_timeout_s: float = DEFAULT_TOOL_TIMEOUT_S) -> None:
        if default_timeout_s <= 0:
            raise ValueError(f"default_timeout_s must be > 0, got {default_timeout_s!r}")
        self._tools: dict[str, ToolDefinition] = {}
        self._default_timeout_s = default_timeout_s

    def register(self, tool: ToolDefinition) -> None:
        """Register a tool; DUPLICATE NAME -> fail fast (M4 §10)."""
        _validate_tool_name(tool.name)
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def requires_confirmation(self, name: str) -> bool:
        tool = self._tools.get(name)
        return bool(tool and tool.mutation and tool.requires_confirmation)

    def activity_label(self, name: str) -> str:
        tool = self._tools.get(name)
        return tool.activity_label if tool else "已执行工具操作"

    def validate_arguments(self, name: str, arguments: dict[str, Any]) -> ToolResult | None:
        """Return a safe validation result, or ``None`` when arguments pass.

        M7.3 uses this before proposing a mutation so validation never calls a
        write implementation.  ``execute`` reuses the same primitive below.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, content="", error="unknown_tool")
        if not isinstance(arguments, dict):
            return ToolResult(ok=False, content="", error="arguments must be a JSON object")
        if tool.input_schema:
            validator = Draft202012Validator(tool.input_schema)
            errors = sorted(validator.iter_errors(arguments), key=lambda e: list(e.path))
            if errors:
                first = errors[0]
                where = ".".join(str(p) for p in first.path) or "(root)"
                return ToolResult(
                    ok=False,
                    content="",
                    error=f"invalid arguments: {where} {first.message}",
                )
        return None

    def provider_schemas(self) -> list[LLMToolSchema]:
        """Provider-neutral declarations for the chat request (M4 §10).
        Agent code never serializes vendor wire JSON itself."""
        return [
            LLMToolSchema(
                name=t.name, description=t.description, input_schema=t.input_schema
            )
            for t in self._tools.values()
        ]

    async def execute(
        self,
        name: str,
        *,
        arguments: dict[str, Any],
        context: ToolContext,
        timeout_s: float | None = None,
    ) -> ToolResult:
        """Validate -> bounded execution -> sanitized ToolResult.

        - unknown tool: ToolResult(ok=False, error="unknown_tool") — no crash
        - jsonschema validation failure: safe validation error (M4 §11)
        - timeout: ToolResult(ok=False, error=<safe timeout>) via wait_for, so
          no task leaks / "Task exception was never retrieved" (M4 §12)
        - implementation exception: sanitized generic error (M4 §12)
        """
        tool = self._tools.get(name)
        validation_error = self.validate_arguments(name, arguments)
        if validation_error is not None:
            return validation_error
        try:
            if timeout_s is None:
                timeout_s = self._default_timeout_s
            result = await asyncio.wait_for(
                tool.execute(context=context, **arguments), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            return ToolResult(
                ok=False,
                content="",
                error=f"tool execution timed out after {timeout_s:g}s",
            )
        except Exception:
            # Sanitized: never expose the traceback to the model (M4 §12).
            return ToolResult(ok=False, content="", error="tool execution failed")
        if not isinstance(result, ToolResult):
            return ToolResult(
                ok=False, content="", error="tool returned an invalid result"
            )
        return result
