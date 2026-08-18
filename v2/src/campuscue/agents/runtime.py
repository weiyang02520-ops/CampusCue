"""CampusAgentRuntime (M4 §30-34) — minimal bounded Tool Loop.

User Input
  -> Conversation (bounded in-memory thread)
  -> ContextBudget (trim/overflow)
  -> Provider.chat(tools=...)
  -> no tool_calls -> final answer
  -> tool_calls -> ToolRegistry.execute each (validated + timed + sanitized)
  -> append assistant tool_calls + tool result messages
  -> Provider again
  -> repeat (max_steps bound)

Defenses (M4 §30/§32):
- max_steps: default 6, hard upper bound 8 (validated in AgentConfig)
- duplicate tool-call loop defense: >=3 CONSECUTIVE identical calls
  (name + canonicalized arguments; tool_call_id deliberately excluded) stop
  the loop with a safe answer
- provider errors map to user-safe Chinese messages (M4 §33); raw bodies never
  shown; zero enabled providers -> "未配置模型服务" (M4 §34)
- context overflow -> graceful safe response (M4 §28)

Provider-neutral: this class sees only LLMToolSchema/LLMToolCall/ToolResult —
never OpenAI wire JSON (M4 §6 hard rule). It never opens DB sessions; tools
reach the DB through TaskService only.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import asyncio

from campuscue.agents.budget import ContextBudget, estimate_tokens
from campuscue.agents.context import AgentContext
from campuscue.agents.conversation import Conversation
from campuscue.agents.prompts import build_agent_system_prompt
from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.models import LLMMessage, LLMRequest, LLMResponse, LLMToolCall
from campuscue.storage.clock import Clock, SystemClock
from campuscue.tools.context import ToolContext
from campuscue.tools.registry import ToolRegistry, canonical_call_identity

logger = logging.getLogger("campuscue.agents.runtime")

# duplicate-call defense: stop after N consecutive identical tool calls
DUPLICATE_CALL_LIMIT = 3

# safe user-facing messages (M4 §33/§34) — never raw server bodies
_PROVIDER_ERROR_UX = {
    ProviderErrorCode.TIMEOUT: "模型响应超时，请稍后重试。",
    ProviderErrorCode.AUTH_ERROR: "模型服务认证失败，请检查配置。",
    ProviderErrorCode.RATE_LIMIT: "请求过于频繁，请稍后再试。",
    ProviderErrorCode.NETWORK: "无法连接模型服务，请稍后再试。",
    ProviderErrorCode.INVALID_MODEL: "模型配置无效，请检查模型配置。",
    ProviderErrorCode.CONTEXT_OVERFLOW: "当前对话内容过长，请简化问题。",
    ProviderErrorCode.SERVER_ERROR: "模型服务暂时不可用，请稍后再试。",
    ProviderErrorCode.MALFORMED_OUTPUT: "模型返回格式异常，请重试。",
    ProviderErrorCode.INVALID_REQUEST: "请求无效，请检查模型配置。",
    ProviderErrorCode.CONFIG_ERROR: "模型服务配置无效，请检查配置。",
    ProviderErrorCode.STRUCTURED_OUTPUT_UNSUPPORTED: "模型服务不支持该功能，请检查配置。",
}

UX_STEPS_EXCEEDED = "处理步骤过多，请简化问题或重新描述。"
UX_DUPLICATE_CALLS = "连续重复操作已中止，请换一种说法重新描述。"
UX_CONTEXT_OVERFLOW = "当前对话内容过长，请开启新对话后重试。"
UX_NO_PROVIDER = "未配置模型服务"
UX_EMPTY_REPLY = "抱歉，我暂时无法回答这个问题。"


class CampusAgentRuntime:
    def __init__(
        self,
        *,
        tools: ToolRegistry,
        provider,  # OpenAICompatibleProvider | None (None = no provider configured)
        timezone: ZoneInfo,
        system_prompt_builder=None,
        clock: Clock | None = None,
        max_context_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        max_steps: int = 6,
        tool_timeout_s: float = 30.0,
        conversation_max_messages: int = 20,
        conversation_max_threads: int = 256,
    ) -> None:
        if not 1 <= max_steps <= 8:
            raise ValueError(f"max_steps must be in [1, 8], got {max_steps!r}")
        if tool_timeout_s <= 0:
            raise ValueError(f"tool_timeout_s must be > 0, got {tool_timeout_s!r}")
        if conversation_max_messages <= 0:
            raise ValueError(
                "conversation_max_messages must be > 0, "
                f"got {conversation_max_messages!r}"
            )
        if conversation_max_threads <= 0:
            raise ValueError(
                "conversation_max_threads must be > 0, "
                f"got {conversation_max_threads!r}"
            )
        self._tools = tools
        self._provider = provider
        self._tz = timezone
        self._clock = clock or SystemClock()
        self._budget = ContextBudget(
            reserve_output_tokens=reserve_output_tokens,
            max_context_tokens=max_context_tokens,
        )
        self._max_steps = max_steps
        self._tool_timeout_s = tool_timeout_s
        self._conversation_max_messages = conversation_max_messages
        self._conversation_max_threads = conversation_max_threads
        self._conversations: dict[str, Conversation] = {}
        self._conversation_locks: dict[str, asyncio.Lock] = {}
        self._conversation_last_used: dict[str, int] = {}
        self._usage_counter = 0
        self._system_prompt_builder = system_prompt_builder or build_agent_system_prompt
        # deterministic call identity -> consecutive streak counter
        self._tool_schemas = tuple(tools.provider_schemas())

    @property
    def conversations(self) -> dict[str, Conversation]:
        return self._conversations

    def _conversation_for_thread(self, thread: str) -> tuple[Conversation, asyncio.Lock]:
        """Return a bounded thread state and its turn-serialization lock.

        Eviction only considers idle threads. A lock is retained while its turn
        runs, so active conversation state cannot be removed underneath a
        provider/tool exchange.
        """
        conversation = self._conversations.get(thread)
        if conversation is None:
            if len(self._conversations) >= self._conversation_max_threads:
                idle = [
                    candidate
                    for candidate, lock in self._conversation_locks.items()
                    if not lock.locked()
                ]
                if not idle:
                    raise RuntimeError("conversation capacity is temporarily exhausted")
                oldest = min(idle, key=lambda candidate: self._conversation_last_used[candidate])
                self._conversations.pop(oldest, None)
                self._conversation_locks.pop(oldest, None)
                self._conversation_last_used.pop(oldest, None)
            conversation = Conversation(self._conversation_max_messages)
            self._conversations[thread] = conversation
            self._conversation_locks[thread] = asyncio.Lock()
        self._usage_counter += 1
        self._conversation_last_used[thread] = self._usage_counter
        return conversation, self._conversation_locks[thread]

    def _provider_ux(self, e: ProviderError) -> str:
        return _PROVIDER_ERROR_UX.get(e.code, "模型服务暂时不可用，请稍后再试。")

    def _system_prompt(self, now: datetime) -> str:
        now_local = now.astimezone(self._tz)
        return self._system_prompt_builder(
            timezone=str(self._tz), current_time_iso=now_local.isoformat()
        )

    def _to_tool_context(self, ctx: AgentContext, user_text: str = "") -> ToolContext:
        return ToolContext(
            platform=ctx.platform,
            source_id=ctx.source_id,
            conversation_id=ctx.conversation_id,
            conversation_type=ctx.conversation_type,
            message_id=ctx.message_id,
            timestamp=ctx.timestamp,
            trace_id=ctx.trace_id,
            timezone=ctx.timezone,
            user_text=user_text or ctx.user_text,
        )

    async def chat(self, *, context: AgentContext, user_text: str) -> str:
        """One agent turn for one user message. Returns the final reply text.
        NEVER raises on provider/tool failures — always a safe user message."""
        text = (user_text or "").strip()
        if not text:
            return UX_EMPTY_REPLY
        if self._provider is None:
            return UX_NO_PROVIDER

        conversation, lock = self._conversation_for_thread(context.thread)
        async with lock:
            conversation.begin_turn(LLMMessage(role="user", content=text))

            system_prompt = self._system_prompt(context.timestamp)
            try:
                reply = await self._run_loop(conversation, system_prompt, text, context)
            except ProviderError as e:
                logger.warning(
                    "agent provider error; thread=%s trace=%s code=%s",
                    context.thread[:8], context.trace_id[:8], e.code.value,
                )
                reply = self._provider_ux(e)
            conversation.append_to_current_turn(
                [LLMMessage(role="assistant", content=reply)]
            )
            return reply

    async def _run_loop(
        self,
        conversation: Conversation,
        system_prompt: str,
        user_text: str,
        context: AgentContext,
    ) -> str:
        tools_tokens = sum(
            estimate_tokens(s.name)
            + estimate_tokens(s.description)
            + estimate_tokens(str(s.input_schema))
            for s in self._tool_schemas
        )
        # M4 §28: budget BEFORE the loop; overflow stops gracefully
        messages, overflow = self._budget.plan(
            conversation=conversation,
            system_prompt=system_prompt,
            current_user_text=user_text,
            tools_tokens=tools_tokens,
        )
        if overflow:
            return UX_CONTEXT_OVERFLOW

        last_identity: str | None = None
        streak = 0
        pending: list[LLMMessage] = []

        for step in range(1, self._max_steps + 1):
            request_messages = (
                [LLMMessage(role="system", content=system_prompt)]
                + messages
                + pending
            )
            response = await self._provider.chat(
                LLMRequest(
                    messages=request_messages,
                    model=self._provider.model,
                    tools=self._tool_schemas or None,
                    tool_choice="auto" if self._tool_schemas else None,
                    timeout_s=None,
                )
            )
            if not response.tool_calls:
                reply = (response.content or "").strip()
                return reply or UX_EMPTY_REPLY

            # ---- execute all tool calls deterministically (sequential, §31) ----
            assistant_msg = LLMMessage(
                role="assistant", content=None, tool_calls=response.tool_calls
            )
            tool_results: list[LLMMessage] = []
            tool_ctx = self._to_tool_context(context, user_text)
            for call in response.tool_calls:
                identity = canonical_call_identity(call.name, call.arguments)
                if identity == last_identity:
                    streak += 1
                else:
                    last_identity = identity
                    streak = 1
                if streak >= DUPLICATE_CALL_LIMIT:
                    logger.warning(
                        "agent duplicate tool calls stopped; tool=%s", call.name
                    )
                    return UX_DUPLICATE_CALLS
                result = await self._tools.execute(
                    call.name,
                    arguments=call.arguments,
                    context=tool_ctx,
                    timeout_s=self._tool_timeout_s,
                )
                tool_results.append(
                    LLMMessage(
                        role="tool",
                        content=result.content or (result.error or ""),
                        tool_call_id=call.id,
                    )
                )
            pending.append(assistant_msg)
            pending.extend(tool_results)
            # committed exchange is complete: safe to trim history if needed
            conversation.append_to_current_turn(pending)
            pending = []
            messages, _overflow = self._budget.plan(
                conversation=conversation,
                system_prompt=system_prompt,
                current_user_text=user_text,
                tools_tokens=tools_tokens,
            )
            if _overflow:
                return UX_CONTEXT_OVERFLOW

        logger.warning("agent max_steps exceeded")
        return UX_STEPS_EXCEEDED
