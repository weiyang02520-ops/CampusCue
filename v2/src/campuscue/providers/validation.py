"""Canonical validation helpers (M2a.2): ONE rule for secret_reference and
provider numeric config, shared by persistence boundary, bootstrap, and
Provider runtime. No duplicated copies in production source.
"""

from __future__ import annotations

import math
import re

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


def validate_secret_reference(value: str | None) -> None:
    """Contract:

    - None -> allowed (no-auth endpoint)
    - valid ENV variable name (^[A-Z][A-Z0-9_]{2,63}$) -> allowed
    - anything else (path/expression/spaces/dashes) -> ValueError
    """
    if value is None:
        return
    if not _ENV_NAME_RE.match(value):
        raise ValueError(f"invalid secret_reference: {value!r} (must be an ENV variable name)")


def is_valid_secret_reference(value: str | None) -> bool:
    try:
        validate_secret_reference(value)
        return True
    except ValueError:
        return False


def validate_provider_config_numeric(
    *,
    timeout_s: float | None = None,
    max_tokens: int | None = None,
    max_context_tokens: int | None = None,
    temperature: float | None = None,
) -> None:
    """Canonical provider numeric contract (M2a.2-B):

    - timeout_s: finite > 0 (NaN/+inf/-inf rejected)
    - max_tokens / max_context_tokens: None or positive int (bool rejected)
    - temperature: None or finite >= 0 (NaN/+inf/-inf rejected; bool rejected)
    """
    if timeout_s is not None:
        if not isinstance(timeout_s, (int, float)) or isinstance(timeout_s, bool):
            raise ValueError(f"timeout_s must be a finite number, got {timeout_s!r}")
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError(f"timeout_s must be finite and > 0, got {timeout_s!r}")
    for name, value in (("max_tokens", max_tokens), ("max_context_tokens", max_context_tokens)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer, got {value!r}")
    if temperature is not None:
        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            raise ValueError(f"temperature must be a finite number, got {temperature!r}")
        if not math.isfinite(temperature) or temperature < 0:
            raise ValueError(f"temperature must be finite and >= 0, got {temperature!r}")


def validate_request_override(
    *,
    timeout_s: float | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> None:
    """Per-request override contract (M2a.2-C): same numeric rules as config.

    LLMRequest does not expose max_context_tokens; it is not validated here.
    """
    validate_provider_config_numeric(
        timeout_s=timeout_s, max_tokens=max_tokens, temperature=temperature
    )
