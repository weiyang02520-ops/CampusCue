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
    """OneBot v11 success: status == 'ok' (or absent) AND retcode == 0 (or absent)."""
    status = payload.get("status")
    retcode = payload.get("retcode")
    if retcode is not None and not isinstance(retcode, int):
        return False
    if retcode not in (None, 0):
        return False
    if status not in (None, "ok"):
        return False
    return True


def validate_response(payload: dict[str, Any]) -> None:
    """Raise ActionError unless the response reports success. Keeps safe fields only."""
    if not is_success(payload):
        retcode = payload.get("retcode")
        if isinstance(retcode, int):
            raise ActionError("unknown", retcode, str(payload.get("msg", "")))
        raise ActionError("unknown", None, "action response missing valid retcode")
