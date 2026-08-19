"""System API routes (M5): health/status/logs/backup/restore/import/export."""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, Request, status

from campuscue.api.schemas import (
    BackupOut,
    ExportOut,
    HealthOut,
    ImportResult,
    LogOut,
    RestoreOut,
    RestoreRequest,
    SystemStatusOut,
)

router = APIRouter(prefix="/system", tags=["system"])


def _deps(request: Request):
    return request.app.state.deps


@router.get("/health", response_model=HealthOut)
async def health(request: Request):
    deps = _deps(request)
    runtime = deps.runtime
    db_ok = deps.database is not None
    adapter_status = runtime.adapter.status() if runtime and runtime.adapter else {}
    return HealthOut(
        status="ok" if runtime and runtime.state.value == "RUNNING" else "degraded",
        runtime=runtime.state.value if runtime else "unknown",
        database="ok" if db_ok else "disabled",
        adapter="connected" if adapter_status.get("connected") else "disconnected",
        reminders="enabled" if deps.reminder_service is not None else "disabled",
        agent="enabled" if deps.agent_runtime is not None else "disabled",
        api="enabled",
    )


@router.get("/status", response_model=SystemStatusOut)
async def system_status(request: Request):
    deps = _deps(request)
    runtime = deps.runtime
    adapter_status = runtime.adapter.status() if runtime and runtime.adapter else {}
    provider_configured = deps.provider_service is not None and len(await deps.provider_service.list_providers()) > 0
    return SystemStatusOut(
        runtime=runtime.state.value if runtime else "unknown",
        uptime_seconds=getattr(runtime, "uptime_seconds", 0.0) if runtime else 0.0,
        components={
            "onebot": adapter_status,
            "realtime_subscribers": deps.realtime.subscriber_count(),
        },
        feature_flags={
            "task_pipeline": bool(deps.task_service),
            "agent": bool(deps.agent_runtime),
            "reminders": bool(deps.reminder_service),
            "api": True,
        },
        provider_configured=provider_configured,
        adapter_connected=bool(adapter_status.get("connected")),
    )


@router.get("/logs", response_model=LogOut)
async def system_logs(
    request: Request,
    level: str | None = None,
    component: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    deps = _deps(request)
    buffer = deps.log_buffer
    items = buffer.list(level=level, component=component, limit=limit, offset=offset)
    total = buffer.total(level=level, component=component)
    return LogOut(items=items, total=total, limit=limit, offset=offset)


@router.post("/backup", response_model=BackupOut)
async def backup(request: Request):
    deps = _deps(request)
    assert deps.system_service is not None
    return await deps.system_service.create_backup()


@router.post("/restore", response_model=RestoreOut)
async def restore(request: Request, payload: RestoreRequest):
    deps = _deps(request)
    assert deps.system_service is not None
    try:
        result = await deps.system_service.restore(payload.backup, confirm_replace=payload.confirm_replace)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return RestoreOut(**result)


@router.post("/import", response_model=ImportResult)
async def import_tasks(request: Request, payload: dict):
    deps = _deps(request)
    assert deps.system_service is not None
    try:
        return await deps.system_service.import_tasks(payload)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e


@router.get("/export", response_model=ExportOut)
async def export_tasks(request: Request):
    deps = _deps(request)
    assert deps.system_service is not None
    return await deps.system_service.export_tasks()
