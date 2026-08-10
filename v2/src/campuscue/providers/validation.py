"""Canonical validation helpers shared by configuration boundary and runtime.

M2a.1-F: one rule for secret_reference, used by BOTH persistence (repo/bootstrap)
and Provider runtime — no duplicated regex.
"""

from __future__ import annotations

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
