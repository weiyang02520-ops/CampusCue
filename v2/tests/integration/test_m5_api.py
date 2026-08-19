"""M5 API integration tests: real isolated SQLite + services + FastAPI."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from zoneinfo import ZoneInfo

from campuscue.api.app import create_app
from campuscue.api.dependencies import APIDependencies
from campuscue.config import ApiConfig
from campuscue.providers.manager import ProviderManager
from campuscue.repositories.repositories import (
    ExtractionRepository,
    ProviderConfigRepository,
    ReminderRepository,
    SettingRepository,
    SourceRepository,
    TaskRepository,
)
from campuscue.services.provider_service import ProviderService
from campuscue.services.reminder_service import NoopScheduler, ReminderService
from campuscue.services.settings_service import SettingsService
from campuscue.services.source_service import SourceService
from campuscue.services.system_service import SystemService
from campuscue.services.task_service import TaskService
from campuscue.storage.database import Database, DatabaseConfig


@pytest.fixture()
def db(tmp_path: Path):
    database = Database(DatabaseConfig(path=tmp_path / "m5.db", env="test"))
    asyncio.run(database.initialize())
    yield database
    asyncio.run(database.dispose())


@pytest.fixture()
def deps(db):
    sf = db.session
    source_repo = SourceRepository(sf)
    task_repo = TaskRepository(sf)
    reminder_repo = ReminderRepository(sf)
    extraction_repo = ExtractionRepository(sf)
    provider_repo = ProviderConfigRepository(sf)
    setting_repo = SettingRepository(sf)

    reminder_service = ReminderService(reminder_repo, task_repo, scheduler=NoopScheduler())
    task_service = TaskService(task_repo, reminder_service=reminder_service)
    source_service = SourceService(source_repo)
    provider_manager = ProviderManager(provider_repo)
    provider_service = ProviderService(provider_repo, provider_manager)
    settings_service = SettingsService(setting_repo)
    system_service = SystemService(sf, task_service, reminder_service=reminder_service, provider_manager=provider_manager)

    deps = APIDependencies(
        config=ApiConfig(enabled=True, port=6200, timezone="Asia/Shanghai"),
        database=db,
        source_service=source_service,
        task_service=task_service,
        reminder_service=reminder_service,
        provider_service=provider_service,
        settings_service=settings_service,
        system_service=system_service,
    )
    return deps


@pytest.fixture()
def client(deps):
    return TestClient(create_app(deps))


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["api"] == "enabled"


def test_task_crud_and_reminders(client):
    # create source
    r = client.post("/api/v1/sources", json={"platform": "onebot", "conversation_id": "123456", "name": "test"})
    assert r.status_code == 201
    source_id = r.json()["id"]

    # create task with deadline -> reminders planned
    deadline = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.post(
        "/api/v1/tasks",
        json={"title": "M5 test task", "category": "homework", "course": "math", "deadline": deadline, "source_id": source_id},
    )
    assert r.status_code == 201, r.text
    task = r.json()
    task_id = task["id"]
    assert task["status"] == "pending"

    # list/filter/search
    r = client.get("/api/v1/tasks", params={"q": "M5 test", "limit": 10})
    assert r.status_code == 200
    assert r.json()["total"] == 1

    # get
    r = client.get(f"/api/v1/tasks/{task_id}")
    assert r.status_code == 200

    # patch title
    r = client.patch(f"/api/v1/tasks/{task_id}", json={"title": "M5 updated"})
    assert r.status_code == 200
    assert r.json()["title"] == "M5 updated"

    # clear deadline with explicit null
    r = client.patch(f"/api/v1/tasks/{task_id}", json={"deadline": None})
    assert r.status_code == 200
    assert r.json()["deadline"] is None

    # complete
    r = client.post(f"/api/v1/tasks/{task_id}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "done"

    # delete
    r = client.delete(f"/api/v1/tasks/{task_id}")
    assert r.status_code == 204

    # 404
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 404


def test_source_delete_preserves_task(client):
    r = client.post("/api/v1/sources", json={"platform": "onebot", "conversation_id": "g1", "name": "g1"})
    source_id = r.json()["id"]
    r = client.post("/api/v1/tasks", json={"title": "keep", "source_id": source_id})
    task_id = r.json()["id"]
    r = client.delete(f"/api/v1/sources/{source_id}")
    assert r.status_code == 204
    # task still readable
    assert client.get(f"/api/v1/tasks/{task_id}").status_code == 200
    # source hidden from list
    assert client.get("/api/v1/sources").json()["total"] == 0


def test_duplicate_source_409(client):
    payload = {"platform": "onebot", "conversation_id": "dup", "name": "d"}
    assert client.post("/api/v1/sources", json=payload).status_code == 201
    assert client.post("/api/v1/sources", json=payload).status_code == 409


def test_settings_patch(client):
    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    assert r.json()["settings"]["timezone"] == "Asia/Shanghai"
    r = client.patch("/api/v1/settings", json={"settings": {"theme": "dark", "message_retention_days": 90}})
    assert r.status_code == 200
    assert r.json()["settings"]["theme"] == "dark"
    # invalid enum
    r = client.patch("/api/v1/settings", json={"settings": {"theme": "neon"}})
    assert r.status_code == 422


def test_provider_crud_and_secret_never_returned(client):
    payload = {
        "name": "deepseek-test",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "secret_reference": "CAMPUSCUE_LLM_API_KEY",
    }
    r = client.post("/api/v1/providers", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["secret_reference"] == "CAMPUSCUE_LLM_API_KEY"
    assert "secret" not in body
    pid = body["id"]
    # invalid secret ref
    r = client.post("/api/v1/providers", json={**payload, "name": "bad", "secret_reference": "not env"})
    assert r.status_code == 422
    # duplicate
    r = client.post("/api/v1/providers", json=payload)
    assert r.status_code == 409
    # patch/delete
    assert client.patch(f"/api/v1/providers/{pid}", json={"enabled": False}).status_code == 200
    assert client.delete(f"/api/v1/providers/{pid}").status_code == 204


def test_backup_restore_export_import(client):
    # seed a source + task
    client.post("/api/v1/sources", json={"platform": "onebot", "conversation_id": "backup-group", "name": "bg"})
    client.post("/api/v1/tasks", json={"title": "backup me", "category": "other"})
    r = client.post("/api/v1/system/backup")
    assert r.status_code == 200
    backup = r.json()
    assert backup["schema_version"] == 3
    assert any(t["title"] == "backup me" for t in backup["data"]["tasks"])

    # mutate then restore
    client.post("/api/v1/tasks", json={"title": "temporary"})
    r = client.post("/api/v1/system/restore", json={"confirm_replace": False, "backup": backup})
    assert r.status_code == 422
    r = client.post("/api/v1/system/restore", json={"confirm_replace": True, "backup": backup})
    assert r.status_code == 200
    assert client.get("/api/v1/tasks", params={"q": "temporary"}).json()["total"] == 0
    assert client.get("/api/v1/tasks", params={"q": "backup me"}).json()["total"] == 1

    # export/import
    exported = client.get("/api/v1/system/export").json()
    assert exported["kind"] == "campuscue.tasks"
    import_payload = {
        "kind": "campuscue.tasks",
        "version": 1,
        "tasks": [
            {"title": "imported task", "task_type": "homework", "deadline": "2026-08-30T00:00:00Z"},
        ],
    }
    r = client.post("/api/v1/system/import", json=import_payload)
    assert r.status_code == 200
    assert r.json()["created"] == 1


def test_auth_required_when_enabled(db, tmp_path):
    from campuscue.api.app import create_app
    from campuscue.api.dependencies import APIDependencies
    from campuscue.repositories.repositories import SourceRepository, TaskRepository
    from campuscue.services.source_service import SourceService
    from campuscue.services.task_service import TaskService

    deps = APIDependencies(
        config=ApiConfig(enabled=True, port=6200, require_auth=True, token="sekrit"),
        database=db,
        source_service=SourceService(SourceRepository(db.session)),
        task_service=TaskService(TaskRepository(db.session)),
    )
    client = TestClient(create_app(deps))
    assert client.get("/api/v1/health").status_code == 401
    assert client.get("/api/v1/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/v1/health", headers={"Authorization": "Bearer sekrit"}).status_code == 200


def test_validation_error_shape(client):
    r = client.post("/api/v1/tasks", json={"title": ""})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"


def test_agent_chat_uses_runtime(deps, client):
    from campuscue.agents.runtime import CampusAgentRuntime
    from campuscue.providers.models import LLMResponse
    from campuscue.tools.registry import ToolRegistry

    class FakeProvider:
        model = "fake"
        max_context_tokens = 4096

        async def chat(self, request):
            return LLMResponse(role="assistant", content="fake answer", usage={}, raw={})

    # create an enabled source
    r = client.post("/api/v1/sources", json={"platform": "onebot", "conversation_id": "agent-group", "name": "a"})
    source_id = r.json()["id"]
    deps.agent_runtime = CampusAgentRuntime(
        tools=ToolRegistry(),
        provider=FakeProvider(),
        timezone=ZoneInfo("Asia/Shanghai"),
        max_context_tokens=4096,
    )
    r = client.post("/api/v1/agent/chat", json={"source_id": source_id, "message": "hello"})
    assert r.status_code == 200
    assert r.json()["message"] == "fake answer"

    # missing source -> 404
    r = client.post("/api/v1/agent/chat", json={"source_id": 9999, "message": "hello"})
    assert r.status_code == 404
