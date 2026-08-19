"""Tasks API routes (M5). Route layer only: validation -> TaskService."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request, status

from campuscue.api.schemas import Page, TaskCreate, TaskOut, TaskUpdate
from campuscue.repositories.repositories import DuplicateError, NotFoundError
from campuscue.services.task_service import DEADLINE_UNSET

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _get_deps(request: Request):
    return request.app.state.deps


@router.get("", response_model=Page[TaskOut])
async def list_tasks(
    request: Request,
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = None,
    course: str | None = None,
    source_id: int | None = None,
    deadline_from: datetime | None = None,
    deadline_to: datetime | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    deps = _get_deps(request)
    assert deps.task_service is not None
    items = await deps.task_service.list_filtered(
        status=status_filter, category=category, course=course, source_id=source_id,
        deadline_from=deadline_from, deadline_to=deadline_to, q=q,
        limit=limit, offset=offset,
    )
    total = await deps.task_service.count_filtered(
        status=status_filter, category=category, course=course, source_id=source_id,
        deadline_from=deadline_from, deadline_to=deadline_to, q=q,
    )
    return Page[TaskOut](items=[TaskOut.model_validate(t) for t in items], total=total, limit=limit, offset=offset)


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(request: Request, payload: TaskCreate):
    deps = _get_deps(request)
    assert deps.task_service is not None and deps.source_service is not None
    if payload.source_id is not None:
        try:
            await deps.source_service.get_source(payload.source_id)
        except NotFoundError:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="source not found")
    try:
        task = await deps.task_service.create_manual_task(
            title=payload.title,
            description=payload.description,
            category=payload.category,
            course=payload.course,
            deadline=payload.deadline,
            priority=payload.priority,
            source_id=payload.source_id,
        )
    except (ValueError, DuplicateError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return TaskOut.model_validate(task)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(request: Request, task_id: int):
    deps = _get_deps(request)
    assert deps.task_service is not None
    try:
        task = await deps.task_service.get_task(task_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut.model_validate(task)


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(request: Request, task_id: int, payload: TaskUpdate):
    deps = _get_deps(request)
    assert deps.task_service is not None
    fields = payload.model_fields_set
    deadline = payload.deadline if "deadline" in fields else DEADLINE_UNSET
    try:
        task = await deps.task_service.update_manual_task(
            task_id,
            title=payload.title,
            description=payload.description,
            category=payload.category,
            course=payload.course,
            deadline=deadline,
            priority=payload.priority,
            status=payload.status,
        )
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    except (ValueError, DuplicateError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)) from e
    return TaskOut.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(request: Request, task_id: int):
    deps = _get_deps(request)
    assert deps.task_service is not None
    try:
        await deps.task_service.delete(task_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return None


@router.post("/{task_id}/complete", response_model=TaskOut)
async def complete_task(request: Request, task_id: int):
    deps = _get_deps(request)
    assert deps.task_service is not None
    try:
        task = await deps.task_service.complete(task_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut.model_validate(task)


@router.post("/{task_id}/dismiss", response_model=TaskOut)
async def dismiss_task(request: Request, task_id: int):
    deps = _get_deps(request)
    assert deps.task_service is not None
    try:
        task = await deps.task_service.dismiss(task_id)
    except NotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    return TaskOut.model_validate(task)
