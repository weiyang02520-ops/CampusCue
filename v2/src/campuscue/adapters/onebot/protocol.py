"""OneBot v11 protocol helpers: outbound action JSON + response validation.

Small and explicit. Business layers never construct these directly (ADR-001);
only the OneBotAdapter uses this module.
"""

from __future__ import annotations

import uuid
from typing import Any


def new_echo() -> str:
    return uuid.uuid4().hex


def build_action(action: str, params: dict[str, Any], echo: str) -> dict[str, Any]:
    """Build a OneBot v11 action request JSON frame."""
    return {"action": action, "params": params, "echo": echo}


class ActionError(Exception):
    """Typed failure for a OneBot action response with non-success status."""

    def __init__(self, action: str, retcode: int | None, message: str) -> None:
        self.action = action
        self.retcode = retcode
        self.message = message
        super().__init__(f"action {action} failed (retcode={retcode}): {message}")


def is_success(payload: dict[str, Any]) -> bool:
    """STRICT OneBot v11 success (M1.1 finding F):

    success requires BOTH status == 'ok' AND retcode == 0.
    Missing either field is malformed -> failure, never success.
    """
    return payload.get("status") == "ok" and payload.get("retcode") == 0


def validate_response(payload: dict[str, Any]) -> None:
    """Raise ActionError unless the response reports success. Keeps safe fields only."""
    if not is_success(payload):
        retcode = payload.get("retcode")
        if isinstance(retcode, int):
            raise ActionError("unknown", retcode, str(payload.get("msg", "")))
        raise ActionError("unknown", None, "action response missing valid retcode")
