"""Providers API routes (M5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from campuscue.api.schemas import Page, ProviderCreate, ProviderOut, ProviderTestOut, ProviderUpdate
from campuscue.repositories.repositories import DuplicateError, NotFoundError
from campuscue.providers.errors import ProviderError

router = APIRouter(prefix="/providers", tags=["providers"])


def _deps(request: Request):
    return request.app.state.deps


@router.get("", response_model=Page[ProviderOut])
async def list_providers(request: Request, limit: int = 50, offset: int = 0):
    deps = _deps(request)
    assert deps.provider_service is not None
    items = await deps.provider_service.list_providers()
    total = len(items)
    return Page[ProviderOut](items=[ProviderOut.model_validate(x) for x in items[offset:offset + limit]], total=total, limit=limit, offset=offset)


@router.post("", response_model=ProviderOut, status_code=status.HTTP_201_CREATED)
async def create_provider(request: Request, payload: ProviderCreate):
    deps = _deps(request)
    assert deps.provider_service is not None
    try:
        cfg = await deps.provider_service.create_provider(**payload.model_dump())
    except DuplicateError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="provider name already exists")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return ProviderOut.model_validate(cfg)


@router.patch("/{provider_id}", response_model=ProviderOut)
async def patch_provider(request: Request, provider_id: int, payload: ProviderUpdate):
    deps = _deps(request)
    assert deps.provider_service is not None
    try:
        cfg = await deps.provider_service.update_provider(provider_id, **payload.model_dump(exclude_unset=True))
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="provider not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return ProviderOut.model_validate(cfg)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(request: Request, provider_id: int):
    deps = _deps(request)
    assert deps.provider_service is not None
    try:
        await deps.provider_service.delete_provider(provider_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="provider not found")
    return None


@router.post("/{provider_id}/test", response_model=ProviderTestOut)
async def test_provider(request: Request, provider_id: int):
    deps = _deps(request)
    assert deps.provider_service is not None
    result = await deps.provider_service.test_provider(provider_id)
    return ProviderTestOut(**result)
