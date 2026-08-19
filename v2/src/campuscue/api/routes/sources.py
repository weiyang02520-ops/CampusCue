"""Sources API routes (M5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from campuscue.api.schemas import Page, SourceCreate, SourceOut, SourceTestOut, SourceUpdate
from campuscue.repositories.repositories import DuplicateError, NotFoundError
from campuscue.services.source_service import SourceServiceError

router = APIRouter(prefix="/sources", tags=["sources"])


def _deps(request: Request):
    return request.app.state.deps


@router.get("", response_model=Page[SourceOut])
async def list_sources(request: Request, limit: int = 50, offset: int = 0):
    deps = _deps(request)
    assert deps.source_service is not None
    items = await deps.source_service.list_sources()
    total = len(items)
    return Page[SourceOut](items=[SourceOut.model_validate(x) for x in items[offset:offset + limit]], total=total, limit=limit, offset=offset)


@router.post("", response_model=SourceOut, status_code=status.HTTP_201_CREATED)
async def create_source(request: Request, payload: SourceCreate):
    deps = _deps(request)
    assert deps.source_service is not None
    try:
        src = await deps.source_service.create_source(
            platform=payload.platform,
            conversation_id=payload.conversation_id,
            name=payload.name,
            enabled=payload.enabled,
            auto_extract=payload.auto_extract,
            context_window=payload.context_window,
            privacy_policy=payload.privacy_policy,
        )
    except (SourceServiceError, DuplicateError) as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return SourceOut.model_validate(src)


@router.patch("/{source_id}", response_model=SourceOut)
async def patch_source(request: Request, source_id: int, payload: SourceUpdate):
    deps = _deps(request)
    assert deps.source_service is not None
    try:
        src = await deps.source_service.update_source(
            source_id,
            name=payload.name,
            enabled=payload.enabled,
            auto_extract=payload.auto_extract,
            context_window=payload.context_window,
            privacy_policy=payload.privacy_policy,
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    except (SourceServiceError, ValueError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return SourceOut.model_validate(src)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(request: Request, source_id: int):
    deps = _deps(request)
    assert deps.source_service is not None
    try:
        await deps.source_service.delete_source(source_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    except DuplicateError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    return None


@router.post("/{source_id}/test", response_model=SourceTestOut)
async def test_source(request: Request, source_id: int):
    deps = _deps(request)
    assert deps.runtime is not None and deps.runtime.adapter is not None
    # First-version: report adapter connectivity without sending chat spam.
    adapter_status = deps.runtime.adapter.status()
    connected = bool(adapter_status.get("connected"))
    return SourceTestOut(
        ok=connected,
        reachable=connected,
        latency_ms=None,
        error_category=None if connected else "disconnected",
        message="adapter connected" if connected else "adapter not connected",
    )
