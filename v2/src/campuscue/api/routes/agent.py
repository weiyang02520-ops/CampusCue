"""Agent API routes (M5). source_id is required; runtime constructs trusted context."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, status

from campuscue.agents.context import AgentContext
from campuscue.api.schemas import AgentChatRequest, AgentChatResponse, AgentThreadOut
from campuscue.core.events import ConversationType
from campuscue.repositories.repositories import NotFoundError

router = APIRouter(prefix="/agent", tags=["agent"])


def _deps(request: Request):
    return request.app.state.deps


@router.post("/chat", response_model=AgentChatResponse)
async def agent_chat(request: Request, payload: AgentChatRequest):
    deps = _deps(request)
    if deps.agent_runtime is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="agent runtime not enabled")
    if deps.source_service is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="source service unavailable")
    try:
        source = await deps.source_service.get_source(payload.source_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    if not source.enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="source is disabled")
    thread = payload.conversation_id or f"api:{source.id}:{source.conversation_id}"
    context = AgentContext(
        platform=source.platform,
        source_id=source.id,
        conversation_id=thread,
        conversation_type=ConversationType.GROUP if source.platform == "onebot" else ConversationType.PRIVATE,
        message_id=f"api-{uuid.uuid4().hex[:16]}",
        timestamp=datetime.now(timezone.utc),
        trace_id=uuid.uuid4().hex,
        timezone=ZoneInfo(deps.config.timezone),
        user_text=payload.message,
    )
    result = await deps.agent_runtime.chat_with_trace(context=context, user_text=payload.message)
    return AgentChatResponse(
        conversation_id=thread,
        message=result.message,
        tool_activity=result.tool_activity,
        confirmation_state=result.confirmation_state,
    )


@router.get("/threads", response_model=list[AgentThreadOut])
async def agent_threads(request: Request):
    deps = _deps(request)
    if deps.agent_runtime is None:
        return []
    rows = deps.agent_runtime.thread_summary()
    return [AgentThreadOut(**r) for r in rows]
