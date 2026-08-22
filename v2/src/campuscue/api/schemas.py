"""M5 API Pydantic schemas (contract)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorOut(BaseModel):
    detail: str
    code: str


# ------------------------------------------------------------------ Tasks

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    category: str = "other"
    course: str | None = None
    deadline: datetime | None = None
    priority: str = "normal"
    source_id: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    description: str | None = None
    category: str | None = None
    course: str | None = None
    deadline: datetime | None = None
    priority: str | None = None
    status: str | None = None


class TaskOut(ApiModel):
    id: int
    title: str
    description: str | None
    category: str
    course: str | None
    deadline: datetime | None
    status: str
    priority: str
    confidence: float | None
    source_id: int | None
    source_message_id: str | None
    source_text_reference: str | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ Sources

class SourceCreate(BaseModel):
    platform: str = "onebot"
    conversation_id: str = Field(..., max_length=64)
    name: str = ""
    enabled: bool = True
    auto_extract: bool = True
    context_window: int = Field(default=5, ge=1)
    privacy_policy: str = "default"


class SourceUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    auto_extract: bool | None = None
    context_window: int | None = Field(default=None, ge=1)
    privacy_policy: str | None = None


class SourceOut(ApiModel):
    id: int
    platform: str
    conversation_id: str
    name: str
    enabled: bool
    auto_extract: bool
    context_window: int
    privacy_policy: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None


class SourceTestOut(BaseModel):
    ok: bool
    reachable: bool
    latency_ms: float | None = None
    error_category: str | None = None
    message: str = ""


# ------------------------------------------------------------------ Messages

class MessageOut(BaseModel):
    id: int
    source_id: int | None
    source_message_id: str
    created_at: datetime
    status: str
    confidence: float | None
    had_task: bool
    task_id: int | None = None
    reason: str | None = None
    text_retained: bool = False
    retained_text: str | None = None


class MessageDetailOut(MessageOut):
    normalized_result: dict[str, Any] | None = None
    audit: dict[str, Any] | None = None
    error: str | None = None


# ------------------------------------------------------------------ Reminders

class ReminderOut(ApiModel):
    id: int
    task_id: int
    trigger_at: datetime
    type: str
    status: str
    last_run: datetime | None
    error: str | None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ Providers

class ProviderCreate(BaseModel):
    name: str
    provider_type: str = "openai_compatible"
    base_url: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    max_context_tokens: int | None = None
    timeout_s: float = 30.0
    secret_reference: str | None = None
    enabled: bool = True


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: str | None = None
    base_url: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    max_context_tokens: int | None = None
    timeout_s: float | None = None
    secret_reference: str | None = None
    enabled: bool | None = None


class ProviderOut(ApiModel):
    id: int
    name: str
    provider_type: str
    base_url: str
    model: str
    temperature: float | None
    max_tokens: int | None
    max_context_tokens: int | None
    timeout_s: float
    secret_reference: str | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ProviderTestOut(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error_category: str | None = None
    message: str = ""


# ------------------------------------------------------------------ Agent

class AgentChatRequest(BaseModel):
    source_id: int
    conversation_id: str | None = None
    message: str = Field(..., min_length=1)


class AgentChatResponse(BaseModel):
    conversation_id: str
    message: str
    tool_activity: list[str] = Field(default_factory=list)
    confirmation_state: str | None = None


class AgentThreadOut(BaseModel):
    conversation_id: str
    source_id: int | None = None
    message_count: int
    last_activity: int | None = None


# ------------------------------------------------------------------ Settings

class SettingsOut(BaseModel):
    settings: dict[str, Any]
    restart_required: list[str] = Field(default_factory=list)


class SettingsPatch(BaseModel):
    settings: dict[str, Any]


# ------------------------------------------------------------------ System

class HealthOut(BaseModel):
    status: str
    runtime: str
    database: str
    adapter: str
    reminders: str
    agent: str
    api: str


class SystemStatusOut(BaseModel):
    runtime: str
    uptime_seconds: float
    components: dict[str, Any]
    feature_flags: dict[str, bool]
    provider_configured: bool
    adapter_connected: bool


class LogOut(BaseModel):
    items: list[dict[str, Any]]
    total: int
    limit: int
    offset: int


class BackupOut(BaseModel):
    format_version: int
    schema_version: int
    created_at: str
    version: str
    data: dict[str, Any]


class RestoreRequest(BaseModel):
    confirm_replace: bool = False
    backup: dict[str, Any]


class RestoreOut(BaseModel):
    restored: bool
    schema_version: int


class ImportResult(BaseModel):
    created: int
    skipped: int
    duplicates: int
    errors: list[dict[str, str]]


class ExportOut(BaseModel):
    kind: str
    version: int
    tasks: list[dict[str, Any]]
