"""M5 minimal API auth: optional Bearer token for non-loopback or explicit auth."""

from __future__ import annotations

import hmac

from fastapi import Depends, HTTPException, Request, status


def require_auth(request: Request) -> None:
    deps = request.app.state.deps
    if not deps.config.require_auth:
        return
    expected = deps.config.token
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else ""
    if expected is None or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing API token",
        )
