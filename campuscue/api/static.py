"""Serve the built board SPA at /campus.

Mount ordering matters. AstrBot's dashboard registers a catch-all
``/{static_path:path}`` route (astrbot/dashboard/api/static_files.py) which would
swallow /campus and hand back the admin dashboard's index.html instead. Because
Starlette matches routes in registration order, these routes only work if they
are added *before* the dashboard's static routes -- which is what
``install_campus_static`` guarantees by inserting at the front of the table
rather than appending.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

DIST = Path(__file__).resolve().parents[1] / "web" / "dist"

NOT_BUILT = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>课讯</title>
<style>
 body{font-family:system-ui,"Microsoft YaHei UI",sans-serif;background:#faf8f4;
      color:#1f1c17;display:grid;place-items:center;min-height:100vh;margin:0}
 main{max-width:32rem;padding:2rem;line-height:1.7}
 code{background:#f2efe8;padding:2px 6px;border-radius:3px}
</style></head>
<body><main>
<h1>看板还没构建</h1>
<p>先构建前端产物：</p>
<pre><code>cd campuscue/web
pnpm install
pnpm build</code></pre>
<p>开发时也可以直接跑 <code>pnpm dev</code>，它会把 API 代理到本进程。</p>
</main></body></html>
"""


def _resolve(relative: str) -> Path | None:
    """Resolve a request path inside dist, refusing anything that escapes it."""
    candidate = (DIST / relative).resolve()
    try:
        candidate.relative_to(DIST.resolve())
    except ValueError:
        # Path traversal attempt, or a symlink pointing outside the bundle.
        return None
    return candidate if candidate.is_file() else None


async def serve_index() -> FileResponse | HTMLResponse:
    index = DIST / "index.html"
    if not index.is_file():
        # A helpful page rather than a 404: the most likely reason for landing
        # here is that the frontend has not been built yet.
        return HTMLResponse(NOT_BUILT, status_code=503)
    return FileResponse(index)


async def serve_asset(asset_path: str) -> FileResponse:
    resolved = _resolve(asset_path)
    if resolved is None:
        raise HTTPException(status_code=404)
    return FileResponse(resolved)


def install_campus_static(app: FastAPI) -> None:
    """Register the board's routes.

    Must be called before ``static_files_router`` is included, which in
    astrbot/dashboard/api/app.py is the very last registration -- so calling this
    immediately before it is enough, and no route reordering is needed.

    Args:
        app: The FastAPI application the dashboard has already configured.
    """
    # response_model=None: these return Response objects, not serialisable data,
    # and FastAPI would otherwise try to build a Pydantic model from the return
    # annotation and fail at import time.
    for path, endpoint in (
        ("/campus", serve_index),
        ("/campus/", serve_index),
        ("/campus/{asset_path:path}", serve_asset),
    ):
        app.add_api_route(
            path,
            endpoint,
            methods=["GET"],
            include_in_schema=False,
            response_model=None,
        )


__all__ = ["DIST", "install_campus_static"]
