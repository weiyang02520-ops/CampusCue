"""Full CampusCue backup: fidelity, validation and all-or-nothing restore."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import reminders, store
from campuscue.api import backup, routes
from campuscue.api.schemas import BACKUP_KIND, BACKUP_VERSION, RestoreIn
from campuscue.models import CampusExtraction, CampusTask

UMO = "aiocqhttp:GroupMessage:backup-7788"


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    db = SQLiteDatabase(str(tmp_path / "campus-backup-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    monkeypatch.setattr(reminders, "_cron", None)
    monkeypatch.setattr(reminders, "_ctx", None)
    try:
        yield db
    finally:
        await db.engine.dispose()


@pytest_asyncio.fixture
async def client(campus_db):
    app = FastAPI()
    app.include_router(routes.router)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://board") as http:
        yield http


async def seed_install() -> CampusTask:
    deadline = datetime.now(timezone.utc) + timedelta(days=3)
    task = CampusTask(
        umo=UMO,
        title="提交完整备份实验",
        task_type="homework",
        deadline=deadline,
        source_group_name="软件工程课程群",
        source_sender_name="张老师",
        raw_text="实验报告周五前提交",
        extract_reason="包含提交与截止时间",
        reminder_job_ids=["machine-local-job"],
    )
    task.dedup_key = store.dedup_key(task.umo, task.title, task.deadline)
    task = await store.create_task(task)
    await store.update_source(
        UMO,
        display_name="软件工程课程群",
        course_name="软件工程",
        authority_senders=["teacher-1"],
        stat_seen=12,
        stat_l1_passed=4,
        stat_tasks_created=1,
    )
    await store.update_profile(
        UMO,
        lead_minutes={"homework": [2880, 120]},
        quiet_hours={"start": "22:30", "end": "07:00"},
        confidence_threshold=0.8,
        auto_confirm=True,
    )
    await store.set_setting("campuscue.notify.target_umo", "qq:FriendMessage:20002")
    await store.record_extraction(
        CampusExtraction(
            umo=UMO,
            task_id=task.task_id,
            outcome="task_created",
            raw_text="实验报告周五前提交",
            l1_score=4.2,
            l1_hits={"keywords": ["提交"]},
            l2_model="test-model",
            l2_raw_response='{"is_task":true}',
            l2_parsed={"is_task": True},
            l3_notes={"phrase": "周五"},
        )
    )
    return task


def empty_backup(**changes) -> dict:
    body = {
        "kind": BACKUP_KIND,
        "version": BACKUP_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tasks": [],
        "sources": [],
        "profiles": [],
        "settings": [],
        "extractions": [],
        "confirm_replace": True,
    }
    body.update(changes)
    return body


@pytest.mark.asyncio
async def test_full_backup_carries_every_campuscue_table_but_not_cron_ids(client):
    task = await seed_install()

    response = await client.get("/campus/backup")

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == BACKUP_KIND
    assert body["version"] == BACKUP_VERSION
    assert [row["task_id"] for row in body["tasks"]] == [task.task_id]
    assert "reminder_job_ids" not in body["tasks"][0]
    assert body["sources"][0]["authority_senders"] == ["teacher-1"]
    assert body["profiles"][0]["confidence_threshold"] == 0.8
    assert body["settings"][0]["value"]["v"] == "qq:FriendMessage:20002"
    assert body["extractions"][0]["l2_raw_response"] == '{"is_task":true}'


@pytest.mark.asyncio
async def test_restore_replaces_all_tables_and_rebuilds_reminders(client, monkeypatch):
    original = await seed_install()
    document = (await client.get("/campus/backup")).json()

    await store.update_task(original.task_id, title="不应保留的修改")
    await store.create_task(
        CampusTask(umo=UMO, title="不应合并的额外任务", task_type="notice")
    )
    await store.update_source("aiocqhttp:GroupMessage:extra", display_name="额外群")

    calls = 0

    async def fake_resync():
        nonlocal calls
        calls += 1
        return {"tasks": 1, "reminders": 2, "cleared": 1}

    monkeypatch.setattr(reminders, "resync_all", fake_resync)
    response = await client.post(
        "/campus/restore", json={**document, "confirm_replace": True}
    )

    assert response.status_code == 200
    assert response.json()["reminders"] == 2
    assert calls == 1
    tasks = await store.list_tasks(
        UMO, statuses=("active", "pending_confirm", "done", "dismissed"), limit=100
    )
    assert [(row.task_id, row.title) for row in tasks] == [
        (original.task_id, "提交完整备份实验")
    ]
    assert tasks[0].reminder_job_ids == []
    assert [row.umo for row in await store.list_sources()] == [UMO]
    assert (await store.get_profile(UMO)).confidence_threshold == 0.8
    assert await store.get_setting("campuscue.notify.target_umo") == (
        "qq:FriendMessage:20002"
    )
    assert (await store.get_task_trace(original.task_id))[0].raw_text == (
        "实验报告周五前提交"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"kind": "campuscue.tasks"},
        {"version": BACKUP_VERSION + 1},
        {"confirm_replace": False},
    ],
)
async def test_wrong_or_unconfirmed_backup_is_rejected_without_writes(client, changes):
    task = await seed_install()

    response = await client.post("/campus/restore", json=empty_backup(**changes))

    assert response.status_code == 422
    assert (await store.get_task(task.task_id)).title == "提交完整备份实验"


@pytest.mark.asyncio
async def test_duplicate_identity_is_rejected_before_replacement(client):
    task = await seed_install()
    document = (await client.get("/campus/backup")).json()
    document["tasks"].append(dict(document["tasks"][0]))

    response = await client.post(
        "/campus/restore", json={**document, "confirm_replace": True}
    )

    assert response.status_code == 422
    assert "重复" in response.text
    assert await store.get_task(task.task_id) is not None


@pytest.mark.asyncio
async def test_invalid_nested_row_is_rejected_before_replacement(client):
    task = await seed_install()
    document = (await client.get("/campus/backup")).json()
    document["sources"][0]["source_type"] = "unknown"

    response = await client.post(
        "/campus/restore", json={**document, "confirm_replace": True}
    )

    assert response.status_code == 422
    assert await store.get_task(task.task_id) is not None


@pytest.mark.asyncio
async def test_database_failure_rolls_back_deletes(campus_db, monkeypatch):
    task = await seed_install()
    document = await backup.export_backup()
    payload = RestoreIn.model_validate(
        {**document.model_dump(mode="json"), "confirm_replace": True}
    )
    original_add_all = AsyncSession.add_all

    def fail_after_staging(self, instances):
        original_add_all(self, instances)
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(AsyncSession, "add_all", fail_after_staging)

    with pytest.raises(RuntimeError, match="synthetic database failure"):
        await backup.replace_from_backup(payload)

    assert (await store.get_task(task.task_id)).title == "提交完整备份实验"
    assert await store.get_setting("campuscue.notify.target_umo") == (
        "qq:FriendMessage:20002"
    )


@pytest.mark.asyncio
async def test_backup_and_restore_require_dashboard_auth_when_enabled(
    client, monkeypatch
):
    from astrbot.dashboard.api import auth

    async def deny(_request):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="login required")

    monkeypatch.setenv("CAMPUSCUE_REQUIRE_AUTH", "1")
    monkeypatch.setattr(auth, "require_dashboard_user", deny)

    exported = await client.get("/campus/backup")
    restored = await client.post("/campus/restore", json=empty_backup())

    assert exported.status_code == 401
    assert restored.status_code == 401
