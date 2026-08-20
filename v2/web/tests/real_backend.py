"""Small isolated M5 API server used by the M6 real Playwright suite."""
from __future__ import annotations

import asyncio
import json
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
        return LLMResponse(role="assistant", content="这是根据当前校园安排生成的确定性回答。", usage={}, raw={})


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
    sources_seed = [
        asyncio.run(sources.create_source(platform="onebot", conversation_id="campus-study", name="学习事务群", enabled=True, auto_extract=True, context_window=5, privacy_policy="default")),
        asyncio.run(sources.create_source(platform="onebot", conversation_id="campus-club", name="社团通知群", enabled=True, auto_extract=True, context_window=5, privacy_policy="default")),
        asyncio.run(sources.create_source(platform="onebot", conversation_id="campus-life", name="校园生活群", enabled=True, auto_extract=False, context_window=3, privacy_policy="default")),
    ]
    source = sources_seed[0]
    seed_tasks = [
        ("高数第三章作业", "高等数学", "homework", 1, "high", "pending", "msg-math"),
        ("英语四级模拟考试", "大学英语", "exam", 2, "normal", "pending", "msg-english"),
        ("机器人实验报告", "机器人实验", "homework", 4, "normal", "pending", "msg-robot"),
        ("确认迎新志愿时间", None, "activity", 5, "normal", "pending_confirm", None),
        ("智能组周会", None, "activity", None, "low", "done", None),
    ]
    for title, course, category, days, priority, task_status, message_id in seed_tasks:
        asyncio.run(task_repo.create(title=title, description=None, category=category, course=course, deadline=datetime.now(timezone.utc) + timedelta(days=days) if days else None, status=task_status, priority=priority, confidence=.95 if message_id else None, source_id=source.id, source_message_id=message_id, source_text_reference=f"校园通知：{title}" if message_id else None))
        if message_id:
            asyncio.run(extraction_repo.create(source_id=source.id, source_message_id=message_id, trace_id=f"trace-{message_id}", provider="CampusCue", model="campus-small", status="success", confidence=.95, normalized_result=json.dumps({"title": title}, ensure_ascii=False), audit=json.dumps({"l5": {}}, ensure_ascii=False)))
    asyncio.run(provider_repo.create(name="校园助手模型", base_url="http://127.0.0.1:6397/v1", model="campus-small", secret_reference="CAMPUSCUE_TEST_KEY", enabled=True))
    fake_provider = CampusAgentRuntime(tools=ToolRegistry(), provider=_Provider(), timezone=ZoneInfo("Asia/Shanghai"), max_context_tokens=4096)
    deps = APIDependencies(config=ApiConfig(enabled=True, host="127.0.0.1", port=6200, require_auth=True, token=TOKEN, timezone="Asia/Shanghai"), runtime=_Runtime(), database=database, source_service=sources, task_service=tasks, reminder_service=reminders, provider_service=providers, settings_service=settings, system_service=system, agent_runtime=fake_provider, realtime=realtime)
    return create_app(deps)


if __name__ == "__main__":
    upstream = ThreadingHTTPServer(("127.0.0.1", 6397), _Upstream); threading.Thread(target=upstream.serve_forever, daemon=True).start()
    uvicorn.run(build_app(), host="127.0.0.1", port=6200, log_level="warning", access_log=False)
