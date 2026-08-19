"""Settings API routes (M5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from campuscue.api.schemas import SettingsOut, SettingsPatch

router = APIRouter(prefix="/settings", tags=["settings"])


def _deps(request: Request):
    return request.app.state.deps


@router.get("", response_model=SettingsOut)
async def get_settings(request: Request):
    deps = _deps(request)
    assert deps.settings_service is not None
    settings = await deps.settings_service.get_all()
    return SettingsOut(settings=settings, restart_required=[])


@router.patch("", response_model=SettingsOut)
async def patch_settings(request: Request, payload: SettingsPatch):
    deps = _deps(request)
    assert deps.settings_service is not None
    try:
        settings = await deps.settings_service.patch(payload.settings)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    restart = deps.settings_service.restart_required_keys(payload.settings)
    return SettingsOut(settings=settings, restart_required=restart)
