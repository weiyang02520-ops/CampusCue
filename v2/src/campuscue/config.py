"""Minimal M1 configuration. Everything configurable, bounded, testable."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OneBotConfig:
    host: str = "127.0.0.1"
    port: int = 6199
    path: str = "/ws"
    access_token: str | None = None  # from env via secret reference; never hardcoded
    action_timeout_s: float = 10.0
    max_pending_actions: int = 32
    dedup_ttl_s: float = 300.0
    dedup_capacity: int = 10000


@dataclass(frozen=True)
class EventBusConfig:
    queue_maxsize: int = 256
    max_in_flight: int = 32


@dataclass(frozen=True)
class RuntimeConfig:
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    event_bus: EventBusConfig = field(default_factory=EventBusConfig)
    diagnostic: bool = False  # CAMPUSCUE_DIAGNOSTIC=1; default OFF (privacy)


_TOKEN_ENV = "CAMPUSCUE_ONEBOT_TOKEN"


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def load_config() -> RuntimeConfig:
    """Load M1 config from environment. Secrets only via env (secret reference)."""
    token = os.environ.get(_TOKEN_ENV) or None
    if token == "":
        token = None
    return RuntimeConfig(
        onebot=OneBotConfig(
            host=os.environ.get("CAMPUSCUE_ONEBOT_HOST", "127.0.0.1"),
            port=int(os.environ.get("CAMPUSCUE_ONEBOT_PORT", "6199")),
            path=os.environ.get("CAMPUSCUE_ONEBOT_PATH", "/ws"),
            access_token=token,
            action_timeout_s=float(os.environ.get("CAMPUSCUE_ACTION_TIMEOUT_S", "10.0")),
            max_pending_actions=int(os.environ.get("CAMPUSCUE_MAX_PENDING_ACTIONS", "32")),
            dedup_ttl_s=float(os.environ.get("CAMPUSCUE_DEDUP_TTL_S", "300.0")),
            dedup_capacity=int(os.environ.get("CAMPUSCUE_DEDUP_CAPACITY", "10000")),
        ),
        event_bus=EventBusConfig(
            queue_maxsize=int(os.environ.get("CAMPUSCUE_QUEUE_MAXSIZE", "256")),
            max_in_flight=int(os.environ.get("CAMPUSCUE_MAX_IN_FLIGHT", "32")),
        ),
        diagnostic=_env_bool("CAMPUSCUE_DIAGNOSTIC"),
    )
