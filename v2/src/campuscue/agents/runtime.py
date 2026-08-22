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
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
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
from campuscue.tools.registry import ToolRegistry, ToolResult, canonical_call_identity
from campuscue.tools.task_tools import _resolve_phrase

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

_CONFIRM_WORDS = {"确认", "可以", "是", "好", "执行", "改吧", "完成吧"}
_REJECT_WORDS = {"取消", "不要", "算了", "不改", "否"}
_AMBIGUOUS_WORDS = {"嗯", "嗯嗯", "看看吧", "随便", "好吧"}


@dataclass(frozen=True)
class AgentTurnResult:
    """Safe per-turn result; the legacy ``chat`` API still returns a string."""

    message: str
    tool_activity: list[str]
    confirmation_state: str | None = None


@dataclass(frozen=True)
class PendingToolApproval:
    """One non-durable, source/thread-bound frozen mutation proposal."""

    thread: str
    source_id: int | None
    tool_name: str
    arguments: dict[str, Any]
    summary: str
    created_turn: int
    message_id: str
    user_text: str


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
        self._conversation_sources: dict[str, int | None] = {}
        self._pending_approvals: dict[str, PendingToolApproval] = {}
        self._usage_counter = 0
        self._system_prompt_builder = system_prompt_builder or build_agent_system_prompt
        # deterministic call identity -> consecutive streak counter
        self._tool_schemas = tuple(tools.provider_schemas())

    @property
    def conversations(self) -> dict[str, Conversation]:
        return self._conversations

    def thread_summary(self) -> list[dict]:
        return [
            {
                "conversation_id": thread,
                "source_id": self._conversation_sources.get(thread),
                "message_count": conv.message_count(),
                "last_activity": self._conversation_last_used.get(thread),
            }
            for thread, conv in self._conversations.items()
        ]

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
                self._conversation_sources.pop(oldest, None)
                self._pending_approvals.pop(oldest, None)
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
        """Compatibility wrapper used by QQ handlers and older callers."""
        result = await self.chat_with_trace(context=context, user_text=user_text)
        return result.message

    async def chat_with_trace(self, *, context: AgentContext, user_text: str) -> AgentTurnResult:
        """Run one bounded turn and return safe activity/confirmation state."""
        text = (user_text or "").strip()
        if not text:
            return AgentTurnResult(UX_EMPTY_REPLY, [])

        conversation, lock = self._conversation_for_thread(context.thread)
        async with lock:
            self._conversation_sources[context.thread] = context.source_id
            conversation.begin_turn(LLMMessage(role="user", content=text))

            pending = self._pending_approvals.get(context.thread)
            if pending is not None:
                if pending.source_id != context.source_id:
                    self._pending_approvals.pop(context.thread, None)
                    result = AgentTurnResult("当前对话来源已变化，原操作已取消，未做修改。", ["已取消待确认操作"], "cancelled")
                    conversation.append_to_current_turn([LLMMessage(role="assistant", content=result.message)])
                    return result
                decision = _parse_confirmation(text)
                if decision == "confirm":
                    self._pending_approvals.pop(context.thread, None)
                    result = await self._execute_pending(pending, context)
                    conversation.append_to_current_turn([LLMMessage(role="assistant", content=result.message)])
                    return result
                if decision == "reject":
                    self._pending_approvals.pop(context.thread, None)
                    result = AgentTurnResult("已取消，这次不会修改任务。", ["已取消待确认操作"], "cancelled")
                    conversation.append_to_current_turn([LLMMessage(role="assistant", content=result.message)])
                    return result
                if decision == "ambiguous":
                    result = AgentTurnResult("如果要执行，请明确回复“确认”或“取消”。", ["等待你的明确确认"], "pending")
                    conversation.append_to_current_turn([LLMMessage(role="assistant", content=result.message)])
                    return result
                # A changed topic invalidates the old proposal. Continue this
                # turn normally; the old frozen arguments are discarded.
                self._pending_approvals.pop(context.thread, None)

            if self._provider is None:
                result = AgentTurnResult(UX_NO_PROVIDER, [])
                conversation.append_to_current_turn([LLMMessage(role="assistant", content=result.message)])
                return result

            system_prompt = self._system_prompt(context.timestamp)
            try:
                result = await self._run_loop(conversation, system_prompt, text, context)
            except ProviderError as e:
                logger.warning(
                    "agent provider error; thread=%s trace=%s code=%s",
                    context.thread[:8], context.trace_id[:8], e.code.value,
                )
                result = AgentTurnResult(self._provider_ux(e), [])
            conversation.append_to_current_turn(
                [LLMMessage(role="assistant", content=result.message)]
            )
            return result

    async def _run_loop(
        self,
        conversation: Conversation,
        system_prompt: str,
        user_text: str,
        context: AgentContext,
    ) -> AgentTurnResult:
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
            return AgentTurnResult(UX_CONTEXT_OVERFLOW, [])

        last_identity: str | None = None
        streak = 0
        pending: list[LLMMessage] = []
        activities: list[str] = []

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
                return AgentTurnResult(reply or UX_EMPTY_REPLY, activities)

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
                    return AgentTurnResult(UX_DUPLICATE_CALLS, activities)
                if self._tools.requires_confirmation(call.name):
                    if call.name in {"task_update", "task_complete", "task_dismiss"}:
                        # Grounding is a real source-scoped read through the
                        # registry, performed before the write can be proposed.
                        activities.append(self._tools.activity_label("task_get"))
                    proposal, proposal_error = await self._propose_mutation(
                        call.name, call.arguments, tool_ctx, context
                    )
                    if proposal_error is not None:
                        result = proposal_error
                        activities.append("未创建待确认操作")
                    else:
                        assert proposal is not None
                        self._pending_approvals[context.thread] = proposal
                        activities.append(f"等待确认：{proposal.summary}")
                        result = ToolResult(
                            ok=False,
                            content="需要用户明确确认后才能执行。",
                            error="confirmation_required",
                        )
                        tool_results.append(
                            LLMMessage(role="tool", content=result.content, tool_call_id=call.id)
                        )
                        pending.append(assistant_msg)
                        pending.extend(tool_results)
                        conversation.append_to_current_turn(pending)
                        return AgentTurnResult(
                            proposal.summary + "确认吗？",
                            activities,
                            "pending",
                        )
                else:
                    result = await self._tools.execute(
                        call.name,
                        arguments=call.arguments,
                        context=tool_ctx,
                        timeout_s=self._tool_timeout_s,
                    )
                    activities.append(self._tools.activity_label(call.name))
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
                return AgentTurnResult(UX_CONTEXT_OVERFLOW, activities)

        logger.warning("agent max_steps exceeded")
        return AgentTurnResult(UX_STEPS_EXCEEDED, activities)

    async def _propose_mutation(
        self,
        name: str,
        arguments: dict[str, Any],
        tool_ctx: ToolContext,
        context: AgentContext,
    ) -> tuple[PendingToolApproval | None, ToolResult | None]:
        validation = self._tools.validate_arguments(name, arguments)
        if validation is not None:
            return None, validation
        frozen = deepcopy(arguments)
        task_data: dict[str, Any] = {}
        if name in {"task_update", "task_complete", "task_dismiss"}:
            task_id = int(arguments["task_id"])
            grounded = await self._tools.execute(
                "task_get", arguments={"task_id": task_id}, context=tool_ctx, timeout_s=self._tool_timeout_s
            )
            if not grounded.ok:
                return None, grounded
            task_data = grounded.data or {}
        if name in {"task_create", "task_update"} and "deadline_phrase" in frozen:
            resolved, error = _resolve_phrase(frozen["deadline_phrase"], context=tool_ctx)
            if error is not None:
                return None, ToolResult(ok=False, content="", error=error)
            assert resolved is not None
            local = resolved.astimezone(tool_ctx.timezone)
            frozen["deadline_phrase"] = f"{local.year}年{local.month}月{local.day}日{local:%H:%M}"
        if name == "task_create":
            summary = f"准备创建任务「{str(frozen['title']).strip()}」"
            if frozen.get("course"):
                summary += f"（{frozen['course']}）"
            if frozen.get("deadline_phrase"):
                summary += f"，截止 {frozen['deadline_phrase']}"
        elif name == "task_update":
            if not any(key in frozen for key in ("title", "course", "deadline_phrase")):
                return None, ToolResult(ok=False, content="", error="至少提供一个要修改的字段")
            title = task_data.get("title") or "当前任务"
            changes: list[str] = []
            if "title" in frozen:
                changes.append(f"标题“{title}”→“{frozen['title']}”")
            if "course" in frozen:
                changes.append(f"课程“{task_data.get('course') or '未设置'}”→“{frozen['course'] or '未设置'}”")
            if "deadline_phrase" in frozen:
                changes.append(f"截止时间→{frozen['deadline_phrase']}")
            summary = f"准备修改「{title}」：" + "；".join(changes)
        elif name == "task_complete":
            summary = f"准备完成「{task_data.get('title') or '当前任务'}」。完成后未触发的提醒会取消"
        else:
            summary = f"准备忽略「{task_data.get('title') or '当前任务'}」。未触发的提醒会取消"
        return PendingToolApproval(
            thread=context.thread,
            source_id=context.source_id,
            tool_name=name,
            arguments=frozen,
            summary=summary,
            created_turn=self._usage_counter,
            message_id=tool_ctx.message_id,
            user_text=tool_ctx.user_text,
        ), None

    async def _execute_pending(self, pending: PendingToolApproval, context: AgentContext) -> AgentTurnResult:
        tool_ctx = self._to_tool_context(
            context,
            user_text=pending.user_text,
        )
        tool_ctx = ToolContext(
            platform=tool_ctx.platform,
            source_id=tool_ctx.source_id,
            conversation_id=tool_ctx.conversation_id,
            conversation_type=tool_ctx.conversation_type,
            message_id=pending.message_id,
            timestamp=tool_ctx.timestamp,
            trace_id=tool_ctx.trace_id,
            timezone=tool_ctx.timezone,
            user_text=pending.user_text,
        )
        result = await self._tools.execute(
            pending.tool_name,
            arguments=deepcopy(pending.arguments),
            context=tool_ctx,
            timeout_s=self._tool_timeout_s,
        )
        if result.ok:
            return AgentTurnResult(result.content, [self._tools.activity_label(pending.tool_name)], "confirmed")
        return AgentTurnResult(
            "操作未完成，未成功修改任务。" if result.error else "操作未完成。",
            ["操作未完成"],
            "confirmed",
        )


def _parse_confirmation(text: str) -> str | None:
    normalized = "".join((text or "").strip().split()).rstrip("。.!！？，,")
    if normalized in _CONFIRM_WORDS:
        return "confirm"
    if normalized in _REJECT_WORDS:
        return "reject"
    if normalized in _AMBIGUOUS_WORDS:
        return "ambiguous"
    return None
