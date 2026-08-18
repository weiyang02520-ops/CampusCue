"""M4 Agent loop tests (test matrix 30-43).

Production paths: REAL OpenAICompatibleProvider (payload builder + parser)
driven by httpx.MockTransport scripted responses; REAL ToolRegistry + REAL
TaskService + real temp SQLite for tool execution. No hand-rolled
provider/tool emulation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import (
    CampusAgentRuntime,
    UX_CONTEXT_OVERFLOW,
    UX_DUPLICATE_CALLS,
    UX_NO_PROVIDER,
    UX_STEPS_EXCEEDED,
)
from campuscue.core.events import ConversationType
from campuscue.providers.models import LLMMessage
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.storage.clock import FixedClock
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import ToolDefinition, ToolRegistry, ToolResult
from campuscue.tools.task_tools import register_task_tools

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 12, 4, 0, 0, tzinfo=timezone.utc)


def _tool_call_body(call_id: str, name: str, arguments: dict) -> dict:
    return {
        "role": "assistant", "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function",
             "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}},
        ],
    }


def _final_body(text: str) -> dict:
    return {"role": "assistant", "content": text}


class _ScriptedProvider:
    """Real OpenAICompatibleProvider + MockTransport playing a response script
    (last script entry repeats). Records every request body for assertions."""

    def __init__(self, script: list[dict], *, max_context_tokens: int | None = 8192) -> None:
        self.seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.seen.append(json.loads(request.content))
            body = script[min(len(self.seen) - 1, len(script) - 1)]
            return httpx.Response(200, json={"choices": [{"message": body}], "usage": {}})

        self.provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1/", model="test-model",
            max_context_tokens=max_context_tokens,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "agent.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
def clock():
    return FixedClock(NOW)


@pytest.fixture
async def services(db, clock):
    from campuscue.repositories.repositories import (
        ReminderRepository,
        SourceRepository,
        TaskRepository,
    )
    from campuscue.services.reminder_service import ReminderService
    from campuscue.services.task_service import TaskService
    from campuscue.tasks.reminder_policy import ReminderPolicy

    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)
    reminder_service = ReminderService(
        reminders, tasks, clock=clock, timezone=TZ,
        policy=ReminderPolicy(min_lead_seconds=60, quiet_start_hour=23, quiet_end_hour=8),
    )
    task_service = TaskService(tasks, clock=clock, reminder_service=reminder_service)
    src = await sources.create(platform="onebot", conversation_id="g1", name="G1")
    return {
        "task_service": task_service,
        "reminder_service": reminder_service,
        "tasks": tasks,
        "source_id": src.id,
    }


def _agent_context(*, source_id=None, conversation_id="g1", message_id="m1"):
    return AgentContext(
        platform="onebot", source_id=source_id, conversation_id=conversation_id,
        conversation_type=ConversationType.GROUP, message_id=message_id,
        timestamp=NOW, trace_id="trace-x", timezone=TZ, user_text="用户原始消息",
    )


def _registry(services, clock, *, with_slow_tool=False):
    r = ToolRegistry(default_timeout_s=0.15)
    register_task_tools(
        r, task_service=services["task_service"],
        reminder_service=services["reminder_service"], tz=TZ, clock=clock,
    )
    if with_slow_tool:
        class _Slow(ToolDefinition):
            name = "slow_probe"
            description = "sleeps"
            input_schema = {"type": "object", "additionalProperties": False}

            async def execute(self, *, context, **kwargs):
                import asyncio

                await asyncio.sleep(30)
                return ToolResult(ok=True, content="late")

        r.register(_Slow())
    return r


def _runtime(services, clock, scripted, *, max_steps=6, tool_timeout=5.0,
             conv_max=20, conv_threads=256, reserve=100, max_ctx=8192):
    return CampusAgentRuntime(
        tools=_registry(services, clock),
        provider=scripted.provider if scripted is not None else None,
        timezone=TZ, clock=clock,
        max_context_tokens=max_ctx, reserve_output_tokens=reserve,
        max_steps=max_steps, tool_timeout_s=tool_timeout,
        conversation_max_messages=conv_max,
        conversation_max_threads=conv_threads,
    )


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_30_no_tool_final_response(self, services, clock):
        scripted = _ScriptedProvider([_final_body("你好！有什么可以帮你？")])
        rt = _runtime(services, clock, scripted)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="你好")
        assert reply == "你好！有什么可以帮你？"
        body = scripted.seen[0]
        assert "tools" in body  # agent requests always carry tools
        assert body["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_31_one_tool_result_then_final(self, services, clock):
        """task_list -> REAL TaskService -> REAL SQLite -> tool result returned
        to provider -> final answer."""
        # seed a task through the production service path
        from campuscue.tasks.models import TaskCandidate

        await services["task_service"].create_task(TaskCandidate(
            title="数第三章作业", category="homework", course="高等数学",
            deadline=NOW + timedelta(days=2), description=None, confidence=1.0,
            dedup_key="k1", source_id=services["source_id"],
            source_message_id="seed1", source_text_reference="", pending_confirm=False,
        ))
        scripted = _ScriptedProvider([
            _tool_call_body("c1", "task_list", {"scope": "open"}),
            _final_body("你这周有 1 个任务。"),
        ])
        rt = _runtime(services, clock, scripted)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="我这周有什么事情？")
        assert reply == "你这周有 1 个任务。"
        # 2nd request carries the assistant tool_calls + tool result message
        second = scripted.seen[1]
        roles = [m["role"] for m in second["messages"]]
        assert roles[-2] == "assistant" and "tool_calls" in second["messages"][-2]
        assert roles[-1] == "tool"
        assert "数第三章作业" in second["messages"][-1]["content"]  # REAL DB data
        assert second["messages"][-1]["tool_call_id"] == "c1"

    @pytest.mark.asyncio
    async def test_31b_task_create_uses_trusted_user_provenance(self, services, clock):
        scripted = _ScriptedProvider([
            _tool_call_body("c1", "task_create", {"title": "模型标题"}),
            _final_body("已创建。"),
        ])
        ctx = _agent_context(source_id=services["source_id"])
        ctx = AgentContext(
            platform=ctx.platform, source_id=ctx.source_id,
            conversation_id=ctx.conversation_id, conversation_type=ctx.conversation_type,
            message_id=ctx.message_id, timestamp=ctx.timestamp, trace_id=ctx.trace_id,
            timezone=ctx.timezone, user_text="请创建一个任务",
        )
        rt = _runtime(services, clock, scripted)
        await rt.chat(context=ctx, user_text="请创建一个任务")
        task = (await services["tasks"].list_for_source(services["source_id"]))[0]
        assert task.source_text_reference == "请创建一个任务"

    @pytest.mark.asyncio
    async def test_31c_second_create_same_source_message_is_rejected(self, services, clock):
        """M2 UNIQUE(source_id, source_message_id) is an explicit first-version
        limit: one Agent user message can create at most one Task. The second
        tool call returns a failure to the model and is never reported created.
        """
        scripted = _ScriptedProvider([
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "create-1", "type": "function", "function": {
                    "name": "task_create", "arguments": '{"title":"英语作文"}',
                }},
                {"id": "create-2", "type": "function", "function": {
                    "name": "task_create", "arguments": '{"title":"高数作业"}',
                }},
            ]},
            _final_body("第一个已创建，第二个未创建。"),
        ])
        rt = _runtime(services, clock, scripted)
        ctx = _agent_context(source_id=services["source_id"], message_id="one-user-message")
        reply = await rt.chat(context=ctx, user_text="帮我添加英语作文和高数作业两个任务")
        assert reply == "第一个已创建，第二个未创建。"
        tasks = await services["tasks"].list_for_source(services["source_id"])
        assert len(tasks) == 1
        tool_messages = scripted.seen[1]["messages"][-2:]
        assert tool_messages[0]["tool_call_id"] == "create-1"
        assert '已创建任务' in tool_messages[0]["content"]
        assert tool_messages[1]["tool_call_id"] == "create-2"
        assert "任务未创建" in tool_messages[1]["content"]
        assert '英语作文' in tasks[0].title

    @pytest.mark.asyncio
    async def test_32_multiple_tool_calls_in_one_response(self, services, clock):
        """Sequential execution (M4 §31) preserves call-id mapping."""
        from campuscue.tasks.models import TaskCandidate

        t = await services["task_service"].create_task(TaskCandidate(
            title="任务A", category="other", course=None, deadline=None,
            description=None, confidence=1.0, dedup_key="k2",
            source_id=services["source_id"], source_message_id="seed2",
            source_text_reference="", pending_confirm=False,
        ))
        assert t.created is True
        task_id = t.task.id
        scripted = _ScriptedProvider([
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "task_get", "arguments": f'{{"task_id": {task_id}}}'}},
                {"id": "c2", "type": "function",
                 "function": {"name": "task_get", "arguments": '{"task_id": 999999}'}},
            ]},
            _final_body("已查看。"),
        ])
        rt = _runtime(services, clock, scripted)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="看看任务")
        assert reply == "已查看。"
        second = scripted.seen[1]
        tail = second["messages"][-3:]
        assert tail[0]["role"] == "assistant" and len(tail[0]["tool_calls"]) == 2
        assert tail[1]["role"] == "tool" and tail[1]["tool_call_id"] == "c1"
        assert tail[2]["role"] == "tool" and tail[2]["tool_call_id"] == "c2"
        assert "任务A" in tail[1]["content"]  # real get result
        assert tail[2]["content"] == "task_not_found"  # safe failure result

    @pytest.mark.asyncio
    async def test_33_max_steps(self, services, clock):
        """Every response requests tools -> loop hits max_steps -> safe stop."""
        script = [_tool_call_body(f"c{i}", "task_get", {"task_id": 1000 + i}) for i in range(10)]
        scripted = _ScriptedProvider(script)
        rt = _runtime(services, clock, scripted, max_steps=3)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="测试")
        assert reply == UX_STEPS_EXCEEDED
        assert len(scripted.seen) == 3  # exactly max_steps provider calls

    @pytest.mark.asyncio
    async def test_34_three_identical_calls_stop(self, services, clock):
        """3 consecutive identical tool calls (name + canonical args, ID
        excluded) -> loop stops with a safe answer."""
        scripted = _ScriptedProvider([_tool_call_body("x1", "task_list", {"scope": "open"})] * 5)
        rt = _runtime(services, clock, scripted)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="查一下")
        assert reply == UX_DUPLICATE_CALLS
        assert len(scripted.seen) == 3  # stopped BEFORE the 3rd execution

    @pytest.mark.asyncio
    async def test_35_provider_timeout_ux(self, services, clock):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("boom", request=request)

        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1/", model="test-model",
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        rt = CampusAgentRuntime(
            tools=_registry(services, clock), provider=provider, timezone=TZ, clock=clock,
            max_context_tokens=8192, reserve_output_tokens=100,
        )
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="hi")
        assert reply == "模型响应超时，请稍后重试。"

    @pytest.mark.asyncio
    async def test_35b_agent_does_not_derive_provider_timeout(self, services, clock):
        """Agent must not override LLMRequest.timeout_s; the Provider's own
        configured timeout remains canonical. tool_timeout_s stays independent."""
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{"message": _final_body("ok")}], "usage": {}})

        provider = OpenAICompatibleProvider(
            base_url="https://api.example.com/v1/", model="test-model", timeout_s=4.25,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        orig = provider.chat

        async def spy(request):
            seen["timeout_s"] = request.timeout_s
            return await orig(request)

        provider.chat = spy  # type: ignore[method-assign]
        rt = CampusAgentRuntime(
            tools=_registry(services, clock), provider=provider, timezone=TZ, clock=clock,
            max_context_tokens=8192, reserve_output_tokens=100, tool_timeout_s=0.05,
        )
        assert await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="hi") == "ok"
        assert seen["timeout_s"] is None  # Agent does not derive/override Provider timeout

    @pytest.mark.asyncio
    async def test_36_no_provider_configured(self, services, clock):
        rt = _runtime(services, clock, None)  # provider=None
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="hi")
        assert reply == UX_NO_PROVIDER

    @pytest.mark.asyncio
    async def test_37_malformed_tool_call_ux(self, services, clock):
        scripted = _ScriptedProvider([
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "task_list", "arguments": "{broken"}},
            ]},
        ])
        rt = _runtime(services, clock, scripted)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="hi")
        assert reply == "模型返回格式异常，请重试。"

    @pytest.mark.asyncio
    async def test_38_tool_timeout_and_error_sanitized_to_provider(self, services, clock):
        """A tool timeout produces a SAFE ToolResult that still returns to the
        provider (loop continues; no crash, no traceback text)."""
        scripted = _ScriptedProvider([
            _tool_call_body("c1", "slow_probe", {}),
            _final_body("工具超时了，我无法完成。"),
        ])
        rt = CampusAgentRuntime(
            tools=_registry(services, clock, with_slow_tool=True),
            provider=scripted.provider, timezone=TZ, clock=clock,
            max_context_tokens=8192, reserve_output_tokens=100,
            tool_timeout_s=0.05,
        )
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="慢速")
        assert reply == "工具超时了，我无法完成。"
        second = scripted.seen[1]
        tool_msg = second["messages"][-1]
        assert tool_msg["role"] == "tool"
        assert "timed out" in tool_msg["content"]
        assert "Traceback" not in tool_msg["content"]

    @pytest.mark.asyncio
    async def test_39_context_trimming_drops_oldest(self, services, clock):
        """Tiny max_context_tokens -> old turns are dropped before the next
        call; the latest turn + protocol stay valid."""
        scripted = _ScriptedProvider([_final_body("好。")])  # final only, no tools
        # budget barely covers system+user+tools schemas: after a few rounds
        # the oldest turns MUST be trimmed before the next provider call
        rt = _runtime(services, clock, scripted, max_ctx=1250, reserve=100, conv_max=20)
        ctx = _agent_context(source_id=services["source_id"])
        for i in range(4):
            await rt.chat(context=ctx, user_text=f"第{i}轮内容" + "填充" * 30)
        # after 4 rounds of (user+assistant) with a small budget, oldest turns
        # must have been trimmed: the last request holds < 8 messages
        last = scripted.seen[-1]
        assert len(last["messages"]) < 8
        assert "填充" in last["messages"][-1]["content"]  # current user kept

    @pytest.mark.asyncio
    async def test_40_impossible_budget_graceful_stop(self, services, clock):
        """reserve + system + user already exceeds max_context_tokens ->
        graceful context-overflow reply, no provider call at all."""
        scripted = _ScriptedProvider([_final_body("好。")])
        rt = _runtime(services, clock, scripted, max_ctx=60, reserve=512)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="测试")
        assert reply == UX_CONTEXT_OVERFLOW
        assert scripted.seen == []  # ZERO provider calls

    def test_40c_current_user_counted_once(self):
        """A budget that fits system+reserve+one user message must not overflow.
        Double-counting the current user (fixed user_tokens AND the live turn)
        would incorrectly stop before any provider call."""
        from campuscue.agents.budget import ContextBudget, _message_tokens, estimate_tokens
        from campuscue.agents.conversation import Conversation
        from campuscue.providers.models import LLMMessage

        user = "当前用户输入"
        system = "system"
        conv = Conversation(20)
        conv.begin_turn(LLMMessage(role="user", content=user))
        reserve = 10
        max_ctx = reserve + estimate_tokens(system) + _message_tokens(
            LLMMessage(role="user", content=user)
        )
        messages, overflow = ContextBudget(
            reserve_output_tokens=reserve, max_context_tokens=max_ctx
        ).plan(conversation=conv, system_prompt=system, current_user_text=user)
        assert overflow is False
        assert [m.content for m in messages if m.role == "user"] == [user]

    @pytest.mark.asyncio
    async def test_40b_loop_budget_recheck_after_tools(self, services, clock):
        """Budget is re-checked after tool exchanges: a HUGE tool result that
        pushes the turn over the budget stops gracefully before a 2nd call."""
        from campuscue.storage.enums import TaskPriority

        # seed enough long tasks that task_list's result is ~1500+ tokens —
        # far beyond any estimation slack
        for i in range(20):
            await services["tasks"].create(
                title=f"任务{i}号" + "这是一个很长的任务标题内容" * 8,
                status="pending", priority=TaskPriority.NORMAL.value,
                source_id=services["source_id"], source_message_id=None,
            )
        scripted = _ScriptedProvider([
            _tool_call_body("c1", "task_list", {"scope": "open"}),
            _final_body("好。"),
        ])
        # 1200 budget: the FIRST provider call fits easily; the huge tool
        # result then overflows the re-check -> graceful stop, no 2nd call
        rt = _runtime(services, clock, scripted, max_ctx=1200, reserve=100)
        reply = await rt.chat(context=_agent_context(source_id=services["source_id"]), user_text="测试")
        assert reply == UX_CONTEXT_OVERFLOW
        assert len(scripted.seen) == 1


class TestConversation:
    @pytest.mark.asyncio
    async def test_41_same_thread_turns_are_serialized(self, services, clock):
        import asyncio

        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def delayed_chat(request):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
            from campuscue.providers.models import LLMResponse

            return LLMResponse(role="assistant", content=f"reply-{calls}")

        class _Provider:
            model = "test-model"
            max_context_tokens = 8192
            chat = staticmethod(delayed_chat)

        rt = CampusAgentRuntime(
            tools=_registry(services, clock), provider=_Provider(), timezone=TZ,
            clock=clock, reserve_output_tokens=100,
        )
        ctx = _agent_context(source_id=services["source_id"])
        first = asyncio.create_task(rt.chat(context=ctx, user_text="first"))
        await started.wait()
        second = asyncio.create_task(rt.chat(context=ctx, user_text="second"))
        await asyncio.sleep(0)
        assert calls == 1
        release.set()
        assert await first == "reply-1"
        assert await second == "reply-2"
        assert [m.content for m in rt.conversations[ctx.thread].snapshot()] == [
            "first", "reply-1", "second", "reply-2",
        ]

    @pytest.mark.asyncio
    async def test_41b_conversation_threads_are_lru_bounded(self, services, clock):
        scripted = _ScriptedProvider([_final_body("ok")])
        rt = _runtime(services, clock, scripted, conv_threads=2)
        for thread in ("g1", "g2", "g3"):
            await rt.chat(
                context=_agent_context(source_id=services["source_id"], conversation_id=thread),
                user_text=thread,
            )
        assert len(rt.conversations) == 2
        assert "onebot:group:g1" not in rt.conversations

    @pytest.mark.asyncio
    async def test_41c_cjk_estimate_is_conservative(self):
        from campuscue.agents.budget import estimate_tokens

        assert estimate_tokens("中文测试") >= 6


    @pytest.mark.asyncio
    async def test_41_per_thread_isolation(self, services, clock):
        scripted = _ScriptedProvider([_final_body("ok")])
        rt = _runtime(services, clock, scripted)
        await rt.chat(context=_agent_context(source_id=services["source_id"], conversation_id="g1"), user_text="a")
        await rt.chat(context=_agent_context(source_id=services["source_id"], conversation_id="g2"), user_text="b")
        assert len(rt.conversations) == 2
        assert "g1" in list(rt.conversations)[0] or any("g1" in k for k in rt.conversations)

    @pytest.mark.asyncio
    async def test_42_max_history_bound(self, services, clock):
        scripted = _ScriptedProvider([_final_body("ok")])
        rt = _runtime(services, clock, scripted, conv_max=4, max_ctx=8192)
        ctx = _agent_context(source_id=services["source_id"])
        for i in range(6):
            await rt.chat(context=ctx, user_text=f"t{i}")
        conv = rt.conversations["onebot:group:g1"]
        assert conv.message_count() <= 4  # bound enforced by Conversation trim

    @pytest.mark.asyncio
    async def test_43_no_cross_thread_contamination(self, services, clock):
        scripted = _ScriptedProvider([_final_body("ok")])
        rt = _runtime(services, clock, scripted)
        c1 = _agent_context(source_id=services["source_id"], conversation_id="g1")
        c2 = _agent_context(source_id=services["source_id"], conversation_id="g2")
        await rt.chat(context=c1, user_text="g1的秘密")
        await rt.chat(context=c2, user_text="g2的问题")
        conv1 = rt.conversations["onebot:group:g1"]
        conv2 = rt.conversations["onebot:group:g2"]
        assert conv1 is not conv2
        snap1 = [m.content for m in conv1.snapshot()]
        assert "g1的秘密" in snap1 and "g2的问题" not in snap1
        snap2 = [m.content for m in conv2.snapshot()]
        assert "g2的问题" in snap2 and "g1的秘密" not in snap2
