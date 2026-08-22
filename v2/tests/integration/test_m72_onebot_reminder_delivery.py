"""M7.2 source-scoped OneBot reminder delivery contract tests."""

from __future__ import annotations

import asyncio
import json
import socket
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from campuscue.config import ReminderConfig, RuntimeConfig, load_config
from campuscue.core.events import ConversationType
from campuscue.core.outbound import OutgoingMessage
from campuscue.storage.clock import FixedClock

TZ = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def env(tmp_path):
    from campuscue.repositories.repositories import ReminderRepository, SourceRepository, TaskRepository
    from campuscue.services.reminder_service import NoopScheduler, ReminderService
    from campuscue.storage.database import Database, DatabaseConfig
    from campuscue.storage.enums import TaskStatus

    db = Database(DatabaseConfig(path=tmp_path / "m72.db", env="test"))
    await db.initialize()
    clock = FixedClock(NOW)
    sources = SourceRepository(db.session, clock=clock)
    tasks = TaskRepository(db.session, clock=clock)
    reminders = ReminderRepository(db.session, clock=clock)
    service = ReminderService(reminders, tasks, scheduler=NoopScheduler(), clock=clock, timezone=TZ)
    yield {"db": db, "clock": clock, "sources": sources, "tasks": tasks, "reminders": reminders, "service": service, "TaskStatus": TaskStatus}
    await db.dispose()


async def _task(env, *, source_id=None, status="pending"):
    return await env["tasks"].create(
        title="高等数学第三章作业",
        course="高等数学",
        deadline=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc),
        source_id=source_id,
        status=status,
    )


@pytest.mark.asyncio
async def test_m7_a09_success_formats_source_scoped_group_message(env):
    from campuscue.services.reminder_delivery import OneBotReminderDelivery

    source = await env["sources"].create(platform="onebot", conversation_id="12345", name="高数课程群")
    task = await _task(env, source_id=source.id)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")
    sent: list[OutgoingMessage] = []

    class Adapter:
        def status(self):
            return {"connected": True}

        async def send(self, message):
            sent.append(message)

    await OneBotReminderDelivery(Adapter(), env["sources"], timezone=TZ).deliver(reminder=reminder, task=task)
    assert len(sent) == 1
    assert sent[0].conversation_id == "12345"
    assert sent[0].conversation_type is ConversationType.GROUP
    assert sent[0].text == "CampusCue 提醒\n高等数学第三章作业\n课程：高等数学\n截止时间：2026-08-28 22:00"
    assert "12345" not in sent[0].text


@pytest.mark.asyncio
async def test_m7_a09_wrong_source_and_no_source_fail_closed(env):
    from campuscue.services.reminder_delivery import OneBotReminderDelivery, ReminderDeliveryError

    task = await _task(env)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")

    class Adapter:
        def status(self):
            return {"connected": True}

        async def send(self, message):
            raise AssertionError("must not send")

    with pytest.raises(ReminderDeliveryError) as exc:
        await OneBotReminderDelivery(Adapter(), env["sources"], timezone=TZ).deliver(reminder=reminder, task=task)
    assert exc.value.code == "delivery:invalid_target"


@pytest.mark.asyncio
async def test_m7_a09_disconnected_persists_safe_failure(env):
    from campuscue.services.reminder_service import NoopScheduler
    from campuscue.services.reminder_delivery import OneBotReminderDelivery

    source = await env["sources"].create(platform="onebot", conversation_id="12345")
    task = await _task(env, source_id=source.id)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")

    class Adapter:
        def status(self):
            return {"connected": False}

        async def send(self, message):
            raise AssertionError("disconnected adapter must not send")

    env["service"].set_delivery(OneBotReminderDelivery(Adapter(), env["sources"], timezone=TZ))
    assert await env["service"].fire(reminder.id) is True
    row = await env["reminders"].get(reminder.id)
    assert row.status == "fired"
    assert row.error == "delivery:adapter_disconnected"
    assert "12345" not in (row.error or "")


@pytest.mark.asyncio
async def test_m7_a09_action_failure_is_classified_and_persisted(env):
    from campuscue.adapters.onebot.adapter import ActionFailure
    from campuscue.services.reminder_delivery import OneBotReminderDelivery

    source = await env["sources"].create(platform="onebot", conversation_id="12345")
    task = await _task(env, source_id=source.id)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")

    class Adapter:
        def status(self):
            return {"connected": True}

        async def send(self, message):
            raise ActionFailure("retcode=10003")

    env["service"].set_delivery(OneBotReminderDelivery(Adapter(), env["sources"], timezone=TZ))
    assert await env["service"].fire(reminder.id) is True
    row = await env["reminders"].get(reminder.id)
    assert row.status == "fired"
    assert row.error == "delivery:action_failed"


@pytest.mark.asyncio
async def test_m7_a09_disabled_deleted_and_non_onebot_sources_send_zero(env):
    from campuscue.services.reminder_delivery import OneBotReminderDelivery, ReminderDeliveryError

    class Adapter:
        def status(self):
            return {"connected": True}

        async def send(self, message):
            raise AssertionError("invalid source must not send")

    adapter = Adapter()
    for index, (platform, enabled, deleted) in enumerate((("onebot", False, False), ("onebot", True, True), ("qq", True, False)), start=1):
        source = await env["sources"].create(platform=platform, conversation_id=f"12{index}", enabled=enabled)
        if deleted:
            await env["sources"].soft_delete(source.id)
        task = await _task(env, source_id=source.id)
        reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")
        with pytest.raises(ReminderDeliveryError):
            await OneBotReminderDelivery(adapter, env["sources"], timezone=TZ).deliver(reminder=reminder, task=task)


@pytest.mark.asyncio
async def test_m7_a09_no_duplicate_sequential_and_concurrent_fire(env):
    from campuscue.services.reminder_service import NoopScheduler

    source = await env["sources"].create(platform="onebot", conversation_id="12345")
    task = await _task(env, source_id=source.id)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")
    calls = []

    class Sink:
        async def deliver(self, *, reminder, task):
            await asyncio.sleep(0.02)
            calls.append(reminder.id)

    env["service"].set_delivery(Sink())
    assert await asyncio.gather(env["service"].fire(reminder.id), env["service"].fire(reminder.id)) == [True, False]
    assert await env["service"].fire(reminder.id) is False
    assert calls == [reminder.id]


def test_m7_a09_delivery_mode_is_closed_and_default_off(monkeypatch):
    assert RuntimeConfig().reminders.delivery_mode == "noop"
    assert ReminderConfig(enabled=True, delivery_mode="onebot").delivery_mode == "onebot"
    with pytest.raises(ValueError):
        ReminderConfig(delivery_mode="email")
    monkeypatch.setenv("CAMPUSCUE_REMINDER_DELIVERY", "email")
    with pytest.raises(ValueError):
        load_config()


def test_m7_a02_real_connection_test_disconnected_path(tmp_path):
    from campuscue.api.app import create_app
    from campuscue.api.dependencies import APIDependencies
    from campuscue.config import ApiConfig
    from campuscue.repositories.repositories import SourceRepository
    from campuscue.services.source_service import SourceService
    from campuscue.storage.database import Database, DatabaseConfig

    class Adapter:
        def status(self):
            return {"connected": False}

    class Runtime:
        adapter = Adapter()

    import asyncio

    db = Database(DatabaseConfig(path=tmp_path / "m72-api.db", env="test"))
    asyncio.run(db.initialize())
    try:
        deps = APIDependencies(
            config=ApiConfig(enabled=True),
            runtime=Runtime(),
            database=db,
            source_service=SourceService(SourceRepository(db.session)),
        )
        client = TestClient(create_app(deps))
        source = client.post("/api/v1/sources", json={"platform": "onebot", "conversation_id": "12345"}).json()
        result = client.post(f"/api/v1/sources/{source['id']}/test")
        assert result.status_code == 200
        assert result.json() == {"ok": False, "reachable": False, "latency_ms": None, "error_category": "disconnected", "message": "adapter not connected"}
    finally:
        asyncio.run(db.dispose())


@pytest.mark.asyncio
async def test_m7_a09_fake_napcat_observes_onebot_group_action(env):
    """Adapter boundary test: the delivery emits a real OneBot-neutral send."""
    from campuscue.services.reminder_delivery import OneBotReminderDelivery

    source = await env["sources"].create(platform="onebot", conversation_id="24680")
    task = await _task(env, source_id=source.id)
    reminder = await env["reminders"].create(task_id=task.id, trigger_at=NOW, type="deadline")
    sent: list[dict] = []

    class AdapterSpy:
        def status(self):
            return {"connected": True}

        async def send(self, message):
            sent.append({"action": "send_group_msg", "params": {"group_id": int(message.conversation_id), "message": message.text}})

    await OneBotReminderDelivery(AdapterSpy(), env["sources"], timezone=TZ).deliver(reminder=reminder, task=task)
    assert sent == [{"action": "send_group_msg", "params": {"group_id": 24680, "message": "CampusCue 提醒\n高等数学第三章作业\n课程：高等数学\n截止时间：2026-08-28 22:00"}}]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.asyncio
async def test_m7_a09_fake_napcat_runtime_group_delivery_exactly_once(tmp_path):
    from websockets.asyncio.client import connect

    from campuscue.app.runtime import CampusRuntime
    from campuscue.config import OneBotConfig, ReminderConfig, RuntimeConfig, TaskPipelineConfig

    port = _free_port()
    cfg = RuntimeConfig(
        onebot=OneBotConfig(port=port, action_timeout_s=2.0),
        tasks=TaskPipelineConfig(enabled=True, database_path=str(tmp_path / "runtime.db"), database_path_explicit=True),
        reminders=ReminderConfig(enabled=True, delivery_mode="onebot", min_lead_seconds=1),
    )
    runtime = CampusRuntime(cfg)
    await runtime.start()
    assert runtime._reminder_scheduler.running is True
    assert type(runtime._reminder_service._delivery).__name__ == "OneBotReminderDelivery"
    ws = await connect(f"ws://127.0.0.1:{port}/ws")
    try:
        source = await runtime._source_repo.create(platform="onebot", conversation_id="24680", name="高数课程群")
        task = await runtime._task_repo.create(
            title="高等数学第三章作业", course="高等数学",
            deadline=datetime(2026, 8, 28, 14, 0, tzinfo=timezone.utc), source_id=source.id,
        )
        reminder = await runtime._reminder_repo.create(
            task_id=task.id, trigger_at=datetime.now(timezone.utc), type="deadline"
        )
        fire = asyncio.create_task(runtime._reminder_service.fire(reminder.id))
        raw = await asyncio.wait_for(ws.recv(), 3)
        frame = json.loads(raw)
        assert frame["action"] == "send_group_msg"
        assert frame["params"]["group_id"] == 24680
        assert frame["params"]["message"] == "CampusCue 提醒\n高等数学第三章作业\n课程：高等数学\n截止时间：2026-08-28 22:00"
        await ws.send(json.dumps({"status": "ok", "retcode": 0, "echo": frame["echo"], "data": {"message_id": 9001}}))
        assert await fire is True
        assert await runtime._reminder_service.fire(reminder.id) is False
        row = await runtime._reminder_repo.get(reminder.id)
        assert row.status == "fired"
        assert row.error is None
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), 0.15)
    finally:
        await ws.close()
        await runtime.stop()
