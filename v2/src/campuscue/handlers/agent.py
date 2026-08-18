"""AgentChatHandler (M4 §35-37) — platform-neutral agent routing handler.

ACTIVATION (M4 §36, deterministic — NO LLM classification to decide wake-up):
- GROUP: only an explicit @self segment activates the Agent. Ambient group
  announcements pass through to the M2 AI-first Task Pipeline unchanged.
- PRIVATE: direct Agent interaction when the M4 Agent is enabled.
- Empty text after activation: not handled (None -> next handler).

The Agent handler is registered BEFORE TaskPipeline in the Router, so an
explicitly Agent-directed message never also runs through automatic Task
Extraction (one user query -> ONE LLM call chain, not extraction + agent).

Business code returns OutgoingMessage; it never builds OneBot action JSON
(ADR-001). All awaits complete inside the handler — no orphan background
tasks, no "Task exception was never retrieved".
"""

from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from campuscue.agents.context import AgentContext
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.core.events import CampusEvent, ConversationType, SegmentType
from campuscue.core.outbound import OutgoingMessage
from campuscue.core.router import RouterResult
from campuscue.repositories.repositories import SourceRepository

logger = logging.getLogger("campuscue.handlers.agent")

# safe fallback when the event source is not (yet) registered in the DB
UNKNOWN_SOURCE_REPLY = "当前会话尚未接入任务数据，请先在设置中启用该会话。"


class AgentChatHandler:
    def __init__(
        self,
        *,
        runtime: CampusAgentRuntime,
        sources: SourceRepository,
        timezone: ZoneInfo,
    ) -> None:
        self._runtime = runtime
        self._sources = sources
        self._tz = timezone

    def _addressed(self, event: CampusEvent) -> bool:
        """Explicit @self segment in a group message (deterministic rule)."""
        for seg in event.segments:
            if seg.type != SegmentType.AT:
                continue
            if str(seg.data.get("qq") or seg.data.get("user_id") or "") == str(event.self_id):
                return True
        return False

    async def handle(self, event: CampusEvent) -> RouterResult:
        if not event.is_message:
            return None
        if event.conversation_type == ConversationType.GROUP:
            if not self._addressed(event):
                return None  # ambient group traffic -> Task Pipeline
        text = (event.text or "").strip()
        if not text:
            return None  # bare @bot or empty private message

        source = await self._sources.get_by_identity(event.platform, event.conversation_id)
        if source is None:
            return OutgoingMessage(
                conversation_id=event.conversation_id,
                conversation_type=event.conversation_type,
                text=UNKNOWN_SOURCE_REPLY,
            )
        if not source.enabled:
            return OutgoingMessage(
                conversation_id=event.conversation_id,
                conversation_type=event.conversation_type,
                text="当前会话未启用助手。",
            )
        source_id = source.id

        context = AgentContext(
            platform=event.platform,
            source_id=source_id,
            conversation_id=event.conversation_id,
            conversation_type=event.conversation_type,
            message_id=event.message_id,
            timestamp=event.timestamp,
            trace_id=event.trace_id,
            timezone=self._tz,
            user_text=text,
        )
        try:
            reply = await self._runtime.chat(context=context, user_text=text)
        except Exception:
            # never let an agent failure escape into the router; safe reply
            logger.exception("agent handler failed; trace=%s", event.trace_id[:8])
            reply = "抱歉，助手暂时不可用，请稍后再试。"
        return OutgoingMessage(
            conversation_id=event.conversation_id,
            conversation_type=event.conversation_type,
            text=reply,
        )
