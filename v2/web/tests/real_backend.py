"""Small isolated M5 API server used by the M6 real Playwright suite."""
from __future__ import annotations

import asyncio
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from campuscue.agents.runtime import CampusAgentRuntime
from campuscue.api.app import create_app
from campuscue.api.dependencies import APIDependencies
from campuscue.api.realtime import RealtimeHub
from campuscue.config import ApiConfig
from campuscue.providers.models import LLMResponse
from campuscue.providers.manager import ProviderManager
from campuscue.repositories.repositories import (ExtractionRepository, ProviderConfigRepository, ReminderRepository, SettingRepository, SourceRepository, TaskRepository)
from campuscue.services.provider_service import ProviderService
from campuscue.services.reminder_service import NoopScheduler, ReminderService
from campuscue.services.settings_service import SettingsService
from campuscue.services.source_service import SourceService
from campuscue.services.system_service import SystemService
from campuscue.services.task_service import TaskService
from campuscue.storage.database import Database, DatabaseConfig
from campuscue.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "web" / "tests" / ".m61-real.db"
TOKEN = "m6-local-test-token"


class _Adapter:
    def status(self):
        return {"connected": True, "adapter": "synthetic"}


class _Runtime:
    class State:
        value = "RUNNING"
    state = State()
    adapter = _Adapter()
    uptime_seconds = 1.0


class _Provider:
    model = "m6-deterministic"
    max_context_tokens = 4096
    async def chat(self, request):
        return LLMResponse(role="assistant", content="这是来自真实 M5 Agent runtime 的确定性回答。", usage={}, raw={})


class _Upstream(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(b'{"id":"m6","choices":[{"message":{"role":"assistant","content":"ok"}}]}')
    def log_message(self, *_args):
        return


def build_app():
    if DB_PATH.exists(): DB_PATH.unlink()
    database = Database(DatabaseConfig(path=DB_PATH, env="test")); asyncio.run(database.initialize())
    sf = database.session; source_repo = SourceRepository(sf); task_repo = TaskRepository(sf); reminder_repo = ReminderRepository(sf); extraction_repo = ExtractionRepository(sf); provider_repo = ProviderConfigRepository(sf); setting_repo = SettingRepository(sf)
    realtime = RealtimeHub(); reminders = ReminderService(reminder_repo, task_repo, scheduler=NoopScheduler()); tasks = TaskService(task_repo, reminder_service=reminders, notifier=realtime); sources = SourceService(source_repo); manager = ProviderManager(provider_repo); providers = ProviderService(provider_repo, manager); settings = SettingsService(setting_repo); system = SystemService(sf, tasks, reminder_service=reminders, provider_manager=manager)
    source = asyncio.run(sources.create_source(platform="onebot", conversation_id="m6-synthetic-source", name="M6 Synthetic Source", enabled=True, auto_extract=True, context_window=5, privacy_policy="default"))
    asyncio.run(tasks.create_manual_task(title="M6 seeded deadline", description="Synthetic integration task", category="homework", course="Integration", deadline=datetime.now(timezone.utc) + timedelta(days=5), priority="normal", source_id=source.id))
    fake_provider = CampusAgentRuntime(tools=ToolRegistry(), provider=_Provider(), timezone=ZoneInfo("Asia/Shanghai"), max_context_tokens=4096)
    deps = APIDependencies(config=ApiConfig(enabled=True, host="127.0.0.1", port=6200, require_auth=True, token=TOKEN, timezone="Asia/Shanghai"), runtime=_Runtime(), database=database, source_service=sources, task_service=tasks, reminder_service=reminders, provider_service=providers, settings_service=settings, system_service=system, agent_runtime=fake_provider, realtime=realtime)
    return create_app(deps)


if __name__ == "__main__":
    upstream = ThreadingHTTPServer(("127.0.0.1", 6397), _Upstream); threading.Thread(target=upstream.serve_forever, daemon=True).start()
    uvicorn.run(build_app(), host="127.0.0.1", port=6200, log_level="warning", access_log=False)
