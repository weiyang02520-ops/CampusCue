"""Provider error taxonomy (M2). Typed, classified; never exposes secrets."""

from __future__ import annotations

from enum import Enum


class ProviderErrorCode(str, Enum):
    TIMEOUT = "timeout"
    AUTH_ERROR = "auth_error"
    RATE_LIMIT = "rate_limit"
    NETWORK = "network"
    INVALID_MODEL = "invalid_model"
    CONTEXT_OVERFLOW = "context_overflow"
    MALFORMED_OUTPUT = "malformed_output"
    INVALID_REQUEST = "invalid_request"
    SERVER_ERROR = "server_error"


class ProviderError(Exception):
    """Typed provider failure. Message must be safe to log (no secrets)."""

    def __init__(self, code: ProviderErrorCode, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(f"[{code.value}] {message}")

    @property
    def safe_message(self) -> str:
        return self.args[0]


class NoProviderConfiguredError(ProviderError):
    def __init__(self) -> None:
        super().__init__(ProviderErrorCode.INVALID_REQUEST, "no enabled provider configured")


class AmbiguousDefaultProviderError(ProviderError):
    def __init__(self, count: int) -> None:
        super().__init__(
            ProviderErrorCode.INVALID_REQUEST,
            f"multiple enabled providers ({count}); exactly one enabled provider is required",
        )
