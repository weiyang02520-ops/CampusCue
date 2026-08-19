"""Reminders API routes (M5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from campuscue.api.schemas import Page, ReminderOut
from campuscue.repositories.repositories import NotFoundError

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _deps(request: Request):
    return request.app.state.deps


@router.get("", response_model=Page[ReminderOut])
async def list_reminders(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    task_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    deps = _deps(request)
    assert deps.database is not None and deps.reminder_service is not None
    from campuscue.repositories.repositories import ReminderRepository
    repo = ReminderRepository(deps.database.session)
    rows = await repo.list_filtered(status=status_filter, task_id=task_id, limit=limit, offset=offset)
    total = await repo.count_filtered(status=status_filter, task_id=task_id)
    return Page[ReminderOut](items=[ReminderOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("/{reminder_id}/cancel", response_model=ReminderOut)
async def cancel_reminder(request: Request, reminder_id: int):
    deps = _deps(request)
    assert deps.reminder_service is not None
    try:
        reminder = await deps.reminder_service.cancel_reminder(reminder_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="reminder not found")
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e)) from e
    return ReminderOut.model_validate(reminder)
