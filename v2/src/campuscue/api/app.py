"""FastAPI application factory (M5)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute

from campuscue.api.auth import require_auth
from campuscue.api.dependencies import APIDependencies
from campuscue.api.realtime import RealtimeHub
from campuscue.api.routes import agent, messages, providers, reminders, settings, sources, system, tasks
from campuscue.api.schemas import ErrorOut, HealthOut
from campuscue.repositories.repositories import DuplicateError, NotFoundError
from campuscue.services.source_service import SourceServiceError


def _status_code(status_code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(status_code, "ERROR")


def create_app(deps: APIDependencies) -> FastAPI:
    app = FastAPI(
        title="CampusCue V2 API",
        version="0.1.0",
        description="CampusCue V2 REST + Realtime API",
    )
    app.state.deps = deps

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_auth)])
    api.include_router(tasks.router)
    api.include_router(sources.router)
    api.include_router(messages.router)
    api.include_router(reminders.router)
    api.include_router(providers.router)
    api.include_router(agent.router)
    api.include_router(settings.router)
    api.include_router(system.router)

    @api.get("/health", response_model=HealthOut)
    async def api_health(request: Request):
        # Reuse the same health payload as /api/v1/system/health.
        from campuscue.api.routes.system import health as system_health
        return await system_health(request)

    @api.get("/stream")
    async def stream(request: Request):
        hub: RealtimeHub = deps.realtime
        sub_id, queue = hub.subscribe()

        async def gen():
            yield ": connected\n\n"
            async for chunk in hub.stream(sub_id, queue):
                yield chunk

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.include_router(api)

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content=ErrorOut(detail=str(exc), code="NOT_FOUND").model_dump())

    @app.exception_handler(DuplicateError)
    async def duplicate_handler(request: Request, exc: DuplicateError):
        return JSONResponse(status_code=409, content=ErrorOut(detail=str(exc), code="CONFLICT").model_dump())

    @app.exception_handler(SourceServiceError)
    async def source_service_handler(request: Request, exc: SourceServiceError):
        return JSONResponse(status_code=409, content=ErrorOut(detail=str(exc), code="CONFLICT").model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=ErrorOut(detail="request validation failed", code="VALIDATION_ERROR").model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorOut(detail=str(exc.detail), code=_status_code(exc.status_code)).model_dump(),
        )

    return app
