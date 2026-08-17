"""M4 ToolRegistry tests (test matrix 10-15).

Production paths: real ToolRegistry + jsonschema validation + asyncio.wait_for
timeout — no re-implemented validation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.core.events import ConversationType
from campuscue.providers.models import LLMToolSchema
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import (
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    canonical_call_identity,
)


def _ctx(**kw):
    base = dict(
        platform="onebot", source_id=1, conversation_id="g1",
        conversation_type=ConversationType.GROUP, message_id="m1",
        timestamp=datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc),
        trace_id="tr", timezone=ZoneInfo("Asia/Shanghai"),
    )
    base.update(kw)
    return ToolContext(**base)


class _OkTool(ToolDefinition):
    name = "ok_tool"
    description = "succeeds"
    input_schema = {
        "type": "object",
        "properties": {"value": {"type": "integer"}},
        "additionalProperties": False,
    }

    async def execute(self, *, context, **kwargs):
        return ToolResult(ok=True, content=f"ok:{kwargs.get('value')}")


class _SlowTool(ToolDefinition):
    name = "slow_tool"
    description = "sleeps"

    async def execute(self, *, context, **kwargs):
        await asyncio.sleep(10)
        return ToolResult(ok=True, content="late")


class _BrokenTool(ToolDefinition):
    name = "broken_tool"
    description = "raises"

    async def execute(self, *, context, **kwargs):
        raise RuntimeError("boom: internal detail")


class _NotToolResultTool(ToolDefinition):
    name = "weird_tool"
    description = "returns non-ToolResult"

    async def execute(self, *, context, **kwargs):
        return "not a ToolResult"


def _registry():
    r = ToolRegistry(default_timeout_s=0.1)
    r.register(_OkTool())
    r.register(_SlowTool())
    r.register(_BrokenTool())
    r.register(_NotToolResultTool())
    return r


class TestRegistryBasics:
    def test_10_register_list_get(self):
        r = _registry()
        names = [t.name for t in r.list()]
        assert "ok_tool" in names and "slow_tool" in names
        assert r.get("ok_tool").name == "ok_tool"
        assert r.get("missing") is None

    def test_10b_provider_schemas_provider_neutral(self):
        r = _registry()
        schemas = r.provider_schemas()
        assert all(isinstance(s, LLMToolSchema) for s in schemas)
        names = {s.name for s in schemas}
        assert "ok_tool" in names
        assert schemas[0].input_schema == _OkTool.input_schema

    def test_11_duplicate_registration_rejected_fail_fast(self):
        r = _registry()
        with pytest.raises(ValueError, match="already registered"):
            r.register(_OkTool())

    def test_11b_invalid_tool_name_rejected(self):
        class _BadName(ToolDefinition):
            name = "bad name!"  # spaces not allowed by protocol

            async def execute(self, *, context, **kwargs):
                return ToolResult(ok=True, content="x")

        r = ToolRegistry()
        with pytest.raises(ValueError, match="invalid tool name"):
            r.register(_BadName())

    @pytest.mark.asyncio
    async def test_12_unknown_tool_safe_failure(self):
        r = _registry()
        result = await r.execute("nope", arguments={}, context=_ctx())
        assert result.ok is False
        assert result.error == "unknown_tool"

    @pytest.mark.asyncio
    async def test_13_json_schema_validation_failure_safe(self):
        """Invalid model-provided arguments -> safe validation error, tool
        implementation NEVER runs."""
        r = _registry()
        result = await r.execute("ok_tool", arguments={"value": "not-an-int"}, context=_ctx())
        assert result.ok is False
        assert "invalid arguments" in (result.error or "")
        assert "traceback" not in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_13b_schema_rejects_stray_scope_fields(self):
        """additionalProperties=False: a model supplying source_id/group id
        inside arguments is rejected — scope can only come from the trusted
        execution context (M4 §13/§14 security boundary)."""
        r = _registry()
        result = await r.execute(
            "ok_tool", arguments={"value": 1, "source_id": 999}, context=_ctx()
        )
        assert result.ok is False
        assert "source_id" in (result.error or "")

    @pytest.mark.asyncio
    async def test_14_tool_timeout(self):
        r = _registry()
        result = await r.execute("slow_tool", arguments={}, context=_ctx(), timeout_s=0.05)
        assert result.ok is False
        assert "timed out" in (result.error or "")

    @pytest.mark.asyncio
    async def test_14b_registry_default_timeout_applies(self):
        """timeout_s not passed -> registry default bound still enforced."""
        r = _registry()  # default_timeout_s=0.1
        result = await r.execute("slow_tool", arguments={}, context=_ctx())
        assert result.ok is False
        assert "timed out" in (result.error or "")

    @pytest.mark.asyncio
    async def test_15_tool_exception_sanitized(self):
        r = _registry()
        result = await r.execute("broken_tool", arguments={}, context=_ctx())
        assert result.ok is False
        assert result.error == "tool execution failed"
        assert "boom" not in (result.error or "")  # internal detail hidden

    @pytest.mark.asyncio
    async def test_15b_non_toolresult_return_rejected(self):
        r = _registry()
        result = await r.execute("weird_tool", arguments={}, context=_ctx())
        assert result.ok is False
        assert "invalid result" in (result.error or "")

    @pytest.mark.asyncio
    async def test_15c_no_leaked_task_exception(self):
        """wait_for + await: the cancelled coroutine is retrieved inside
        execute — no 'Task exception was never retrieved' warning."""
        r = _registry()
        import warnings

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            await r.execute("slow_tool", arguments={}, context=_ctx(), timeout_s=0.01)
            assert not [x for x in w if "never retrieved" in str(x.message)]


class TestCallIdentity:
    def test_canonical_identity_excludes_tool_call_id(self):
        a = canonical_call_identity("task_list", {"scope": "open"})
        b = canonical_call_identity("task_list", {"scope": "open"})
        assert a == b
        c = canonical_call_identity("task_list", {"scope": "week"})
        assert a != c
        d = canonical_call_identity("task_get", {"task_id": 1})
        assert a != d
