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
    # NOTE: no prefilter threshold — LocalSignalAnalyzer score is NOT a gate
    # (ADR-013 AI-first: local signals are hints, never a semantic veto)
    # NOTE: reminder enablement/knobs live in ReminderConfig only (M3.1-A:
    # one configuration truth — no duplicate reminders_enabled here).


@dataclass(frozen=True)
class ReminderConfig:
    """M3 reminder policy knobs (bounded, fail-fast, configurable)."""

    enabled: bool = False  # CAMPUSCUE_REMINDERS=1
    timezone: str = "Asia/Shanghai"
    min_lead_seconds: float = 60.0
    quiet_start_hour: int = 23
    quiet_end_hour: int = 8


@dataclass(frozen=True)
class AgentConfig:
    """M4 Agent knobs (few, bounded, fail-fast; all consumed by CampusRuntime).

    enabled        CAMPUSCUE_AGENT=1 (default OFF)
    max_steps      tool loop provider-call bound (default 6, hard max 8)
    tool_timeout_s per-tool execution bound
    conversation_max_messages in-memory thread bound
    reserve_output_tokens reserved for the final answer in ContextBudget
    """

    enabled: bool = False
    max_steps: int = 6
    tool_timeout_s: float = 30.0
    conversation_max_messages: int = 20
    conversation_max_threads: int = 256
    reserve_output_tokens: int = 512

    def __post_init__(self) -> None:
        if not 1 <= self.max_steps <= 8:
            raise ValueError(f"max_steps must be in [1, 8], got {self.max_steps!r}")
        if self.tool_timeout_s <= 0:
            raise ValueError(f"tool_timeout_s must be > 0, got {self.tool_timeout_s!r}")
        if self.conversation_max_messages <= 0:
            raise ValueError(
                f"conversation_max_messages must be > 0, got {self.conversation_max_messages!r}"
            )
        if self.conversation_max_threads <= 0:
            raise ValueError(
                f"conversation_max_threads must be > 0, got {self.conversation_max_threads!r}"
            )
        if not 0 < self.reserve_output_tokens <= 8192:
            raise ValueError(
                f"reserve_output_tokens must be in (0, 8192], got {self.reserve_output_tokens!r}"
            )


@dataclass(frozen=True)
class ApiConfig:
    """M5 FastAPI/Realtime configuration (default loopback, disabled)."""

    enabled: bool = False  # CAMPUSCUE_API=1
    host: str = "127.0.0.1"
    port: int = 6200
    require_auth: bool = False  # CAMPUSCUE_REQUIRE_AUTH=1
    token: str | None = None  # CAMPUSCUE_API_TOKEN
    sse_queue_size: int = 32
    sse_heartbeat_interval: float = 15.0
    timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError(f"invalid api port: {self.port!r}")
        if self.sse_queue_size <= 0:
            raise ValueError(f"sse_queue_size must be > 0, got {self.sse_queue_size!r}")
        if self.sse_heartbeat_interval <= 0:
            raise ValueError(f"sse_heartbeat_interval must be > 0, got {self.sse_heartbeat_interval!r}")
        if self.host not in ("127.0.0.1", "localhost", "::1") and not (self.require_auth and self.token):
            raise ValueError(
                "non-loopback API host requires CAMPUSCUE_REQUIRE_AUTH=1 and CAMPUSCUE_API_TOKEN"
            )


@dataclass(frozen=True)
class RuntimeConfig:
    onebot: OneBotConfig = field(default_factory=OneBotConfig)
    event_bus: EventBusConfig = field(default_factory=EventBusConfig)
    tasks: TaskPipelineConfig = field(default_factory=TaskPipelineConfig)
    reminders: ReminderConfig = field(default_factory=ReminderConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
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


def _validate_api_config(api: ApiConfig, tasks: TaskPipelineConfig) -> None:
    if api.enabled and not tasks.enabled:
        raise ConfigError(
            "CAMPUSCUE_API=1 requires CAMPUSCUE_TASK_PIPELINE=1 "
            "(API exposes real DB-backed services)"
        )


def _validate_agent_config(agent: AgentConfig, tasks: TaskPipelineConfig) -> None:
    """M4 §40 fail-fast invariant: the Agent REQUIRES the task pipeline/DB
    foundation (real TaskService + source context). Agent enabled while the
    pipeline is disabled is a configuration error — never a fake in-memory
    TaskService Agent."""
    if agent.enabled and not tasks.enabled:
        raise ConfigError(
            "CAMPUSCUE_AGENT=1 requires CAMPUSCUE_TASK_PIPELINE=1 "
            "(Agent tools run on real TaskService/DB data)"
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
    agent = AgentConfig(
        enabled=_env_bool("CAMPUSCUE_AGENT"),
        max_steps=int(os.environ.get("CAMPUSCUE_AGENT_MAX_STEPS", "6")),
        tool_timeout_s=float(os.environ.get("CAMPUSCUE_AGENT_TOOL_TIMEOUT_S", "30")),
        conversation_max_messages=int(
            os.environ.get("CAMPUSCUE_AGENT_CONVERSATION_MAX", "20")
        ),
        conversation_max_threads=int(
            os.environ.get("CAMPUSCUE_AGENT_CONVERSATION_MAX_THREADS", "256")
        ),
        reserve_output_tokens=int(
            os.environ.get("CAMPUSCUE_AGENT_RESERVE_OUTPUT", "512")
        ),
    )
    _validate_agent_config(agent, tasks)
    api_token = os.environ.get("CAMPUSCUE_API_TOKEN") or None
    api = ApiConfig(
        enabled=_env_bool("CAMPUSCUE_API"),
        host=os.environ.get("CAMPUSCUE_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("CAMPUSCUE_API_PORT", "6200")),
        require_auth=_env_bool("CAMPUSCUE_REQUIRE_AUTH"),
        token=api_token,
        sse_queue_size=int(os.environ.get("CAMPUSCUE_API_SSE_QUEUE", "32")),
        sse_heartbeat_interval=float(os.environ.get("CAMPUSCUE_API_SSE_HEARTBEAT", "15")),
        timezone=os.environ.get("CAMPUSCUE_TIMEZONE", "Asia/Shanghai"),
    )
    _validate_api_config(api, tasks)
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
        agent=agent,
        api=api,
        diagnostic=_env_bool("CAMPUSCUE_DIAGNOSTIC"),
    )
