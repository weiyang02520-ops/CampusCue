"""Messages API routes (M5) — extraction/processed-event projection only."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request, status

from campuscue.api.schemas import MessageDetailOut, MessageOut, Page
from campuscue.repositories.repositories import NotFoundError

router = APIRouter(prefix="/messages", tags=["messages"])


def _deps(request: Request):
    return request.app.state.deps


def _parse_json(value: str | None):
    if not value:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


async def _to_message(deps, row, *, detail: bool = False):
    task = None
    if row.source_id is not None and row.source_message_id:
        try:
            task = await deps.task_service.find_by_source_message(row.source_id, row.source_message_id)
        except Exception:
            task = None
    base = MessageOut(
        id=row.id,
        source_id=row.source_id,
        source_message_id=row.source_message_id,
        created_at=row.created_at,
        status=row.status,
        confidence=row.confidence,
        had_task=row.status == "success" and task is not None,
        task_id=task.id if task else None,
        reason=(_parse_json(row.audit) or {}).get("l5", {}).get("dedup") if row.audit else None,
        text_retained=bool(task and task.source_text_reference),
        retained_text=task.source_text_reference if task and task.source_text_reference else None,
    )
    if not detail:
        return base
    return MessageDetailOut(
        **base.model_dump(),
        normalized_result=_parse_json(row.normalized_result),
        audit=_parse_json(row.audit),
        error=row.error,
    )


@router.get("", response_model=Page[MessageOut])
async def list_messages(
    request: Request,
    source_id: int | None = None,
    had_task: bool | None = None,
    confidence_min: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    deps = _deps(request)
    assert deps.database is not None
    from campuscue.repositories.repositories import ExtractionRepository
    repo = ExtractionRepository(deps.database.session)
    rows = await repo.list_filtered(
        source_id=source_id, had_task=had_task, confidence_min=confidence_min,
        limit=limit, offset=offset,
    )
    total = await repo.count_filtered(source_id=source_id, had_task=had_task, confidence_min=confidence_min)
    items = [await _to_message(deps, r) for r in rows]
    return Page[MessageOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/{message_id}", response_model=MessageDetailOut)
async def get_message(request: Request, message_id: int):
    deps = _get_deps(request)
    assert deps.database is not None
    from campuscue.repositories.repositories import ExtractionRepository
    try:
        row = await ExtractionRepository(deps.database.session).get(message_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="message not found")
    return await _to_message(deps, row, detail=True)


def _get_deps(request: Request):
    return request.app.state.deps
