"""M4 provider tool-protocol tests (test matrix 1-9).

PRODUCTION paths only: real OpenAICompatibleProvider payload builder + parser
via httpx.MockTransport — never a re-implementation of the wire logic.
"""

from __future__ import annotations

import json

import httpx
import pytest

from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.models import LLMMessage, LLMRequest, LLMToolCall, LLMToolSchema
from campuscue.providers.openai_compatible import OpenAICompatibleProvider


def _make_provider(*, handler=None, **kw):
    if handler is None:
        handler = lambda r: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})
    return OpenAICompatibleProvider(
        base_url="https://api.example.com/v1/", model="gpt-4o", **kw,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


_TOOLS = (
    LLMToolSchema(
        name="task_list",
        description="list tasks",
        input_schema={"type": "object", "properties": {"scope": {"type": "string"}}},
    ),
)


# ---------------------------------------------------------------- 1-2: request serialization

class TestToolRequestSerialization:
    @pytest.mark.asyncio
    async def test_1_tool_request_serializes_correctly(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        p = _make_provider(handler=handler)
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            model="gpt-4o",
            tools=_TOOLS,
            tool_choice="auto",
        ))
        tools = seen["body"]["tools"]
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        fn = tools[0]["function"]
        assert fn["name"] == "task_list"
        assert fn["description"] == "list tasks"
        assert fn["parameters"] == _TOOLS[0].input_schema
        assert seen["body"]["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_1b_tool_choice_defaults_to_auto_when_tools_present(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        p = _make_provider(handler=handler)
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            model="gpt-4o",
            tools=_TOOLS,
        ))
        assert seen["body"]["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_2_ordinary_m2_request_unchanged(self):
        """tools=None -> NO tools/tool_choice keys at all (exact M2 wire)."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        p = _make_provider(handler=handler)
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"
        ))
        assert "tools" not in seen["body"]
        assert "tool_choice" not in seen["body"]
        assert seen["body"]["messages"] == [{"role": "user", "content": "hi"}]


# ---------------------------------------------------------------- 3-6: response parsing

class TestToolResponseParsing:
    @pytest.mark.asyncio
    async def test_3_content_null_tool_call_accepted(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "task_list", "arguments": "{\"scope\": \"open\"}"}},
                ],
            }}],
        }))
        resp = await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert resp.content == ""  # tool-only response
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].id == "call_1"
        assert resp.tool_calls[0].name == "task_list"
        assert resp.tool_calls[0].arguments == {"scope": "open"}  # PARSED dict, not JSON string

    @pytest.mark.asyncio
    async def test_4_final_text_response_accepted(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "你本周有2个任务"}}],
        }))
        resp = await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert resp.content == "你本周有2个任务"
        assert resp.tool_calls == ()

    @pytest.mark.asyncio
    async def test_5_malformed_tool_arguments_rejected(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "task_list", "arguments": "{not json"}},
                ],
            }}],
        }))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_5b_tool_arguments_non_object_rejected(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [
                    {"id": "call_1", "type": "function",
                     "function": {"name": "task_list", "arguments": "[1,2,3]"}},
                ],
            }}],
        }))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_6_missing_content_and_tool_calls_rejected(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant"}}],
        }))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_6b_mixed_content_and_tool_calls_rejected(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": "ignored",
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "task_list", "arguments": "{}"},
                }],
            }}],
        }))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_6c_missing_tool_call_id_rejected(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "type": "function",
                    "function": {"name": "task_list", "arguments": "{}"},
                }],
            }}],
        }))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_9_multiple_tool_calls_preserve_ids_and_order(self):
        p = _make_provider(handler=lambda r: httpx.Response(200, json={
            "choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [
                    {"id": "c1", "type": "function", "function": {"name": "task_list", "arguments": "{}"}},
                    {"id": "c2", "type": "function", "function": {"name": "task_get", "arguments": "{\"task_id\": 7}"}},
                ],
            }}],
        }))
        resp = await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert [c.id for c in resp.tool_calls] == ["c1", "c2"]
        assert [c.name for c in resp.tool_calls] == ["task_list", "task_get"]
        assert resp.tool_calls[1].arguments == {"task_id": 7}


# ---------------------------------------------------------------- 7-8: message reserialization

class TestMessageReserialization:
    @pytest.mark.asyncio
    async def test_7_assistant_tool_call_message_reserializes(self):
        """An assistant tool-call message (content=None) must reach the wire
        as {role, content:null, tool_calls:[...]} with arguments JSON-encoded."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "ok"}}]})

        p = _make_provider(handler=handler)
        history = [
            LLMMessage(role="user", content="我这周有什么事情？"),
            LLMMessage(
                role="assistant", content=None,
                tool_calls=(LLMToolCall(id="c9", name="task_list", arguments={"scope": "open"}),),
            ),
            LLMMessage(role="tool", tool_call_id="c9", content="当前会话任务共 0 个。"),
        ]
        await p.chat(LLMRequest(messages=history, model="gpt-4o"))
        wire = seen["body"]["messages"]
        assert wire[1] == {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "c9", "type": "function",
                            "function": {"name": "task_list", "arguments": "{\"scope\": \"open\"}"}}],
        }
        assert wire[2] == {"role": "tool", "tool_call_id": "c9", "content": "当前会话任务共 0 个。"}

    @pytest.mark.asyncio
    async def test_8_tool_result_message_requires_tool_call_id(self):
        p = _make_provider()
        with pytest.raises(ValueError, match="tool_call_id"):
            await p.chat(LLMRequest(
                messages=[LLMMessage(role="tool", content="x")], model="gpt-4o"
            ))
