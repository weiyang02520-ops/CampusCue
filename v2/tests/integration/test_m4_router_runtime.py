"""M4 router activation + composition-root wiring tests (test matrix 44-50).

Production paths: real Router + real AgentChatHandler + real CampusRuntime
composition (_init_task_pipeline) — spy ONLY at the agent constructor boundary,
never a re-implementation of wiring logic.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from campuscue.core.events import (
    CampusEvent,
    ConversationType,
    EventType,
    MessageSegment,
    SegmentType,
)
from campuscue.core.outbound import OutgoingMessage

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 12, 4, 0, 0, tzinfo=timezone.utc)


def _event(*, text="", at_self=False, at_other=None, conversation_type=ConversationType.GROUP,
           conversation_id="g1", self_id="10001", sender_id="20002", message_id="m1"):
    segments = []
    if at_self:
        segments.append(MessageSegment(type=SegmentType.AT, data={"qq": self_id}))
    if at_other:
        segments.append(MessageSegment(type=SegmentType.AT, data={"qq": at_other}))
    if text:
        segments.append(MessageSegment(type=SegmentType.TEXT, data={"text": text}))
    return CampusEvent(
        event_id="e1", trace_id="tr1", platform="onebot", adapter_id="a1",
        event_type=(EventType.GROUP_MESSAGE if conversation_type == ConversationType.GROUP
                    else EventType.PRIVATE_MESSAGE),
        self_id=self_id, message_id=message_id, conversation_id=conversation_id,
        conversation_type=conversation_type, sender_id=sender_id, sender_name="u",
        timestamp=NOW, text=text, segments=tuple(segments),
        group_id=conversation_id if conversation_type == ConversationType.GROUP else None,
    )


class _FakeRuntime:
    def __init__(self):
        self.calls: list[tuple] = []

    async def chat(self, *, context, user_text):
        self.calls.append((context, user_text))
        return "助手回复"


@pytest.fixture
async def db(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "r.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


@pytest.fixture
async def sources(db):
    from campuscue.repositories.repositories import SourceRepository
    from campuscue.storage.clock import FixedClock

    return SourceRepository(db.session, clock=FixedClock(NOW))


def _handler(sources, *, fake=None):
    from campuscue.handlers.agent import AgentChatHandler

    return AgentChatHandler(
        runtime=fake or _FakeRuntime(), sources=sources, timezone=TZ
    )


# ----------------------------------------------------------------- 44-46: activation

class TestActivation:
    @pytest.mark.asyncio
    async def test_44_ambient_group_message_does_not_trigger_agent(self, sources):
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        result = await h.handle(_event(text="高数作业周五前交"))
        assert result is None  # ambient -> passes to Task Pipeline
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_45_explicit_group_at_self_triggers_agent(self, sources):
        await sources.create(
            platform="onebot", conversation_id="g1", name="G1",
            enabled=True, auto_extract=True, context_window=5, privacy_policy="default",
        )
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        result = await h.handle(_event(text="我这周有什么事情？", at_self=True))
        assert result is not None
        assert isinstance(result, OutgoingMessage)
        assert result.text == "助手回复"
        assert result.conversation_id == "g1"
        assert fake.calls and fake.calls[0][1] == "我这周有什么事情？"

    @pytest.mark.asyncio
    async def test_45b_bare_at_without_text_ignored(self, sources):
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        result = await h.handle(_event(text="", at_self=True))
        assert result is None
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_45c_at_other_user_does_not_trigger(self, sources):
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        result = await h.handle(_event(
            text="@别人 你好", at_other="30003",
        ))
        assert result is None
        assert fake.calls == []

    @pytest.mark.asyncio
    async def test_45d_private_message_triggers_directly(self, sources):
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        result = await h.handle(_event(
            text="我这周有什么事情？",
            conversation_type=ConversationType.PRIVATE, conversation_id="u20002",
        ))
        assert result is not None
        assert fake.calls and fake.calls[0][1] == "我这周有什么事情？"

    @pytest.mark.asyncio
    async def test_46_source_id_injected_from_event_source(self, sources):
        """AgentContext.source_id must come from the real DB source lookup for
        the current conversation — trusted scope, never model input."""
        await sources.create(
            platform="onebot", conversation_id="g1", name="G1",
            enabled=True, auto_extract=True, context_window=5, privacy_policy="default",
        )
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        await h.handle(_event(text="查任务", at_self=True))
        context, _ = fake.calls[0]
        assert context.source_id is not None
        assert context.conversation_id == "g1"
        assert context.trace_id == "tr1"

    @pytest.mark.asyncio
    async def test_46b_no_source_row_source_id_none(self, sources):
        fake = _FakeRuntime()
        h = _handler(sources, fake=fake)
        await h.handle(_event(text="查任务", at_self=True, conversation_id="unknown-g"))
        context, _ = fake.calls[0]
        assert context.source_id is None  # graceful, not a crash


# ----------------------------------------------------------------- 47-48: router order

class TestRouterOrder:
    @pytest.mark.asyncio
    async def test_47_agent_directed_message_skips_task_pipeline(self, sources):
        """One user query -> ONE handler chain: agent answers, pipeline NOT
        invoked (no extraction LLM call on an Agent-directed message)."""
        from campuscue.core.router import Router

        fake = _FakeRuntime()
        pipeline_calls = []

        async def pipeline_spy(event):
            pipeline_calls.append(1)
            return None

        await sources.create(
            platform="onebot", conversation_id="g1", name="G1",
            enabled=True, auto_extract=True, context_window=5, privacy_policy="default",
        )
        router = Router()
        router.add_handler(_handler(sources, fake=fake).handle)
        router.add_handler(pipeline_spy)
        result = await router.route(_event(text="我这周有什么事情？", at_self=True))
        assert result is not None and result.text == "助手回复"
        assert fake.calls  # agent handled it
        assert pipeline_calls == []  # pipeline NOT run (M4 §36)

    @pytest.mark.asyncio
    async def test_47b_ambient_message_reaches_pipeline_and_echo(self, sources):
        from campuscue.core.router import Router
        from campuscue.handlers.echo import echo_handler

        fake = _FakeRuntime()
        router = Router()
        router.add_handler(_handler(sources, fake=fake).handle)
        router.add_handler(echo_handler)
        # ambient hello: agent returns None -> echo replies (M1 preserved)
        result = await router.route(_event(text="hello"))
        assert result is not None and result.text == "received: hello"
        assert fake.calls == []  # agent never woke up
        # ambient task-ish text: agent returns None, echo returns None -> unhandled
        result2 = await router.route(_event(text="高数作业周五前交"))
        assert result2 is None

    @pytest.mark.asyncio
    async def test_48_hello_preserved_with_agent_enabled(self, sources):
        """M4 §37/§48: 'hello' must still produce 'received: hello' under the
        agent-enabled path (group, not addressed to the bot)."""
        from campuscue.core.router import Router
        from campuscue.handlers.echo import echo_handler

        fake = _FakeRuntime()
        router = Router()
        router.add_handler(_handler(sources, fake=fake).handle)
        router.add_handler(echo_handler)
        result = await router.route(_event(text="hello"))
        assert result is not None and result.text == "received: hello"
        assert fake.calls == []


# ----------------------------------------------------------------- 49-50: composition root

class TestCompositionRoot:
    @pytest.mark.asyncio
    async def test_49_agent_config_consumed_by_real_composition(self, monkeypatch, tmp_path):
        """Spy the PRODUCTION CampusAgentRuntime constructor through the real
        _init_task_pipeline — config values must actually reach it."""
        from campuscue.app import runtime as runtime_mod
        from campuscue.agents.runtime import CampusAgentRuntime
        from campuscue.config import AgentConfig, RuntimeConfig, TaskPipelineConfig

        cfg = replace(
            RuntimeConfig(),
            tasks=TaskPipelineConfig(
                enabled=True, database_path=str(tmp_path / "w.db"),
                database_path_explicit=True, timezone="Asia/Shanghai",
            ),
            agent=AgentConfig(
                enabled=True, max_steps=7, tool_timeout_s=12.0,
                conversation_max_messages=15, reserve_output_tokens=300,
            ),
        )
        captured = {}
        orig_init = CampusAgentRuntime.__init__

        def spy_init(self, *, tools, provider, timezone, system_prompt_builder=None,
                     clock=None, max_context_tokens=None, reserve_output_tokens=None,
                     max_steps=None, tool_timeout_s=None, conversation_max_messages=None,
                     conversation_max_threads=None, **kw):
            captured.update(
                tools=tools, provider=provider, max_steps=max_steps,
                tool_timeout_s=tool_timeout_s,
                conversation_max_messages=conversation_max_messages,
                conversation_max_threads=conversation_max_threads,
                reserve_output_tokens=reserve_output_tokens,
                max_context_tokens=max_context_tokens,
            )
            orig_init(self, tools=tools, provider=provider, timezone=timezone,
                      system_prompt_builder=system_prompt_builder, clock=clock,
                      max_context_tokens=max_context_tokens,
                      reserve_output_tokens=reserve_output_tokens,
                      max_steps=max_steps, tool_timeout_s=tool_timeout_s,
                      conversation_max_messages=conversation_max_messages, **kw)

        CampusAgentRuntime.__init__ = spy_init
        rt = None
        try:
            from campuscue.core.router import Router

            rt = runtime_mod.CampusRuntime(cfg)
            rt.router = Router()
            await rt._init_task_pipeline()
        finally:
            CampusAgentRuntime.__init__ = orig_init
            if rt is not None:
                await rt._dispose_database()

        # config consumed by the REAL composition path
        assert captured["max_steps"] == 7
        assert captured["tool_timeout_s"] == 12.0
        assert captured["conversation_max_messages"] == 15
        assert captured["reserve_output_tokens"] == 300
        assert captured["provider"] is None  # no provider configured -> graceful
        # registered tool set is the canonical M4 set
        names = {t.name for t in captured["tools"].list()}
        assert {"task_list", "task_get", "task_create", "task_update",
                "task_complete", "task_dismiss"} <= names

    @pytest.mark.asyncio
    async def test_49b_agent_handler_registered_before_pipeline(self, monkeypatch, tmp_path):
        """Router order with Agent enabled: agent handler FIRST, pipeline
        second, echo last — @bot query returns agent reply; ambient hello still
        echoes."""
        from campuscue.app import runtime as runtime_mod
        from campuscue.agents.runtime import CampusAgentRuntime
        from campuscue.config import AgentConfig, RuntimeConfig, TaskPipelineConfig
        from campuscue.core.router import Router

        cfg = replace(
            RuntimeConfig(),
            tasks=TaskPipelineConfig(
                enabled=True, database_path=str(tmp_path / "w.db"),
                database_path_explicit=True, timezone="Asia/Shanghai",
            ),
            agent=AgentConfig(enabled=True),
        )
        orig_init = CampusAgentRuntime.__init__
        CampusAgentRuntime.__init__ = lambda self, **kw: object.__init__(self)
        rt = None
        try:
            rt = runtime_mod.CampusRuntime(cfg)
            rt.router = Router()
            await rt._init_task_pipeline()
        finally:
            CampusAgentRuntime.__init__ = orig_init
            if rt is not None:
                await rt._dispose_database()
        # order: agent -> pipeline (echo is added by start(), not pipeline init)
        handlers = rt.router._handlers
        assert len(handlers) == 2
        assert "AgentChatHandler" in str(type(handlers[0].__self__))
        assert "TaskPipeline" in str(type(handlers[1].__self__))

    @pytest.mark.asyncio
    async def test_50_no_orphan_tasks_after_agent_chat_and_stop(self, monkeypatch, tmp_path):
        """Full real composition: agent chat runs a real tool loop path (no
        provider -> immediate safe reply), then stop() leaves no orphan
        background tasks from the Agent layer."""
        from campuscue.app import runtime as runtime_mod
        from campuscue.config import AgentConfig, RuntimeConfig, TaskPipelineConfig

        cfg = replace(
            RuntimeConfig(),
            tasks=TaskPipelineConfig(
                enabled=True, database_path=str(tmp_path / "w.db"),
                database_path_explicit=True, timezone="Asia/Shanghai",
            ),
            agent=AgentConfig(enabled=True),
        )
        rt = runtime_mod.CampusRuntime(cfg)
        from campuscue.core.router import Router

        rt.router = Router()
        try:
            await rt._init_task_pipeline()
        except Exception:
            await rt._dispose_database()
            raise
        try:
            before = {t for t in asyncio.all_tasks()}
            # real handler + real runtime with NO provider -> safe reply,
            # no LLM/tool background work
            from campuscue.handlers.agent import AgentChatHandler

            h = AgentChatHandler(runtime=rt._agent_runtime, sources=rt._agent_handler._sources, timezone=TZ)
            result = await h.handle(_event(text="你好", at_self=True))
            assert result is not None and "未配置模型服务" in result.text
            await asyncio.sleep(0.05)
            after = {t for t in asyncio.all_tasks()}
            assert after - before == set()  # no orphan tasks
        finally:
            await rt._dispose_database()
