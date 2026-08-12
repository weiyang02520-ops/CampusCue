"""Minimal M1 configuration. Everything configurable, bounded, testable."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo


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
class TaskPipelineConfig:
    enabled: bool = False  # CAMPUSCUE_TASK_PIPELINE=1 (M2 opt-in; M1 works without)
    database_path: str = "data/campuscue.db"
    database_path_explicit: bool = False  # CAMPUSCUE_DB_PATH was actually supplied
    timezone: str = "Asia/Shanghai"
    confidence_threshold: float = 0.6
    reminders_enabled: bool = False  # CAMPUSCUE_REMINDERS=1 (M3 opt-in)
    # NOTE: no prefilter threshold — LocalSignalAnalyzer score is NOT a gate
    # (ADR-013 AI-first: local signals are hints, never a semantic veto)


@dataclass(frozen=True)
class ReminderConfig:
    """M3 reminder policy knobs (bounded, fail-fast, configurable)."""

    enabled: bool = False  # CAMPUSCUE_REMINDERS=1
    timezone: str = "Asia/Shanghai"
    min_lead_seconds: float = 60.0
    quiet_start_hour: int = 23
    quiet_end_hour: int = 8


@dataclass(frozen=True)
class RuntimeConfig:
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    event_bus: EventBusConfig = field(default_factory=EventBusConfig)
    tasks: TaskPipelineConfig = field(default_factory=TaskPipelineConfig)
    reminders: ReminderConfig = field(default_factory=ReminderConfig)
    diagnostic: bool = False  # CAMPUSCUE_DIAGNOSTIC=1; default OFF (privacy)

    def __post_init__(self) -> None:
        # Fail-fast validation (M1.1 finding D): every "bounded" knob must be a
        # positive number. asyncio.Queue(maxsize=0) means UNBOUNDED, which would
        # silently break the M1 bounded design.
        self._require_positive("queue_maxsize", self.event_bus.queue_maxsize)
        self._require_positive("max_in_flight", self.event_bus.max_in_flight)
        self._require_positive("max_pending_actions", self.onebot.max_pending_actions)
        self._require_positive("dedup_capacity", self.onebot.dedup_capacity)
        self._require_positive("dedup_ttl_s", self.onebot.dedup_ttl_s)
        self._require_positive("action_timeout_s", self.onebot.action_timeout_s)
        self._require_positive("min_lead_seconds", self.reminders.min_lead_seconds)
        if not (0 <= self.reminders.quiet_start_hour < 24):
            raise ValueError(f"invalid quiet_start_hour: {self.reminders.quiet_start_hour!r}")
        if not (0 <= self.reminders.quiet_end_hour < 24):
            raise ValueError(f"invalid quiet_end_hour: {self.reminders.quiet_end_hour!r}")
        if not (1 <= self.onebot.port <= 65535):
            raise ValueError(f"invalid port: {self.onebot.port!r} (must be 1-65535)")
        if not self.onebot.path.startswith("/"):
            raise ValueError(f"invalid path: {self.onebot.path!r} (must start with '/')")

    @staticmethod
    def _require_positive(name: str, value: float) -> None:
        if value is None or value <= 0:
            raise ValueError(f"{name} must be > 0, got {value!r}")


class ConfigError(ValueError):
    """Safe, classified configuration failure (fail-fast before runtime start)."""


def _validate_task_config(tasks: TaskPipelineConfig, *, env: str) -> None:
    """M2b.1.1 (Finding G + config validation):

    1. confidence_threshold must be finite and 0 <= x <= 1.
    2. timezone must resolve via ZoneInfo when the task pipeline is enabled.
    3. TEST-SAFETY INVARIANT: CAMPUSCUE_ENV=test + pipeline enabled + DB path
       not explicitly supplied -> FAIL (test environment must have NO automatic
       path to the normal/production DB, including the default data/campuscue.db).
    """
    if not tasks.enabled:
        return
    threshold = tasks.confidence_threshold
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or not math.isfinite(threshold):
        raise ConfigError(f"confidence_threshold must be finite, got {threshold!r}")
    if not 0.0 <= threshold <= 1.0:
        raise ConfigError(f"confidence_threshold must be in [0, 1], got {threshold!r}")
    try:
        ZoneInfo(tasks.timezone)
    except Exception as e:
        raise ConfigError(f"invalid timezone {tasks.timezone!r}: {e}") from None
    if env == "test" and not tasks.database_path_explicit:
        raise ConfigError(
            "CAMPUSCUE_ENV=test with the task pipeline enabled requires an explicit "
            "CAMPUSCUE_DB_PATH (isolated test database). Refusing to fall back to "
            f"the default application DB ({tasks.database_path!r})."
        )


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
    env = os.environ.get("CAMPUSCUE_ENV", "production")
    db_path = os.environ.get("CAMPUSCUE_DB_PATH")
    tasks = TaskPipelineConfig(
        enabled=_env_bool("CAMPUSCUE_TASK_PIPELINE"),
        database_path=db_path if db_path is not None else "data/campuscue.db",
        database_path_explicit=db_path is not None,
        timezone=os.environ.get("CAMPUSCUE_TIMEZONE", "Asia/Shanghai"),
        confidence_threshold=float(os.environ.get("CAMPUSCUE_CONFIDENCE_THRESHOLD", "0.6")),
    )
    _validate_task_config(tasks, env=env)
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
        tasks=tasks,
        reminders=ReminderConfig(
            enabled=_env_bool("CAMPUSCUE_REMINDERS"),
            timezone=os.environ.get("CAMPUSCUE_REMINDER_TIMEZONE", "Asia/Shanghai"),
            min_lead_seconds=float(os.environ.get("CAMPUSCUE_REMINDER_MIN_LEAD_S", "60")),
            quiet_start_hour=int(os.environ.get("CAMPUSCUE_REMINDER_QUIET_START", "23")),
            quiet_end_hour=int(os.environ.get("CAMPUSCUE_REMINDER_QUIET_END", "8")),
        ),
        diagnostic=_env_bool("CAMPUSCUE_DIAGNOSTIC"),
    )
