"""API dependency container. Routes read services from request.app.state.deps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from campuscue.api.logbuffer import LogBuffer
from campuscue.api.realtime import RealtimeHub
from campuscue.config import ApiConfig
from campuscue.services.reminder_service import ReminderService
from campuscue.services.settings_service import SettingsService
from campuscue.services.source_service import SourceService
from campuscue.services.system_service import SystemService
from campuscue.services.task_service import TaskService


@dataclass
class APIDependencies:
    config: ApiConfig
    runtime: Any = None
    database: Any = None
    source_service: SourceService | None = None
    task_service: TaskService | None = None
    reminder_service: ReminderService | None = None
    provider_service: Any = None
    settings_service: SettingsService | None = None
    system_service: SystemService | None = None
    agent_runtime: Any = None
    agent_handler: Any = None
    realtime: RealtimeHub = field(default_factory=RealtimeHub)
    log_buffer: LogBuffer = field(default_factory=LogBuffer)
