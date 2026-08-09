"""Tasks in and out as JSON: the round trip, and the ways it can go wrong.

The feature exists so a task list can move between installs -- laptop to demo
machine, one student's export into another's board. What makes that hard is not
serialisation, it is everything the file must *not* carry: reminder job ids that
name rows in the writing machine's cron table, and a group id that may not exist
on the reading machine. Both are pinned here.

The other half is idempotence. A student will re-import the same file, and will
import onto a machine that already watched the same group and extracted the same
notice by itself. Neither may double the board.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import notify, reminders, store
from campuscue.api import routes, transfer
from campuscue.api.schemas import TRANSFER_KIND, TRANSFER_VERSION
from campuscue.models import CampusTask, as_utc

UMO = "aiocqhttp:GroupMessage:transfer-7788"
OTHER_UMO = "aiocqhttp:GroupMessage:transfer-9900"


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    """A throwaway database, patched in where the store looks for it.

    Without this the import endpoint writes into the live ``data/data_v4.db`` --
    the running app's own board -- which is exactly the failure this suite would
    be least likely to notice.
    """
    db = SQLiteDatabase(str(tmp_path / "campus-transfer-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    monkeypatch.setattr(routes, "DEFAULT_UMO", UMO)
    monkeypatch.setattr(reminders, "_cron", None)
    monkeypatch.setattr(reminders, "_ctx", None)

    async def no_toast(title, body):
        return True

    monkeypatch.setattr(notify, "show_toast", no_toast)
    try:
        yield db
    finally:
        await db.engine.dispose()


@pytest_asyncio.fixture
async def client(campus_db):
    app = FastAPI()
    app.include_router(routes.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://board") as http:
        yield http


async def make_task(**kw) -> CampusTask:
    defaults = {
        "umo": UMO,
        "title": "提交软件工程实验三报告",
        "task_type": "homework",
        "status": "active",
        "deadline": datetime.now(timezone.utc) + timedelta(days=3),
        "confidence": 0.9,
        "source_kind": "group",
        "source_group_name": "软件工程课程群",
        "source_sender_name": "张老师",
        "raw_text": "实验三报告周五晚上12点前提交",
        "extract_reason": "包含截止关键词与明确时间",
    }
    defaults.update(kw)
    task = CampusTask(**defaults)
    task.dedup_key = store.dedup_key(task.umo, task.title, task.deadline)
    return await store.create_task(task)


def doc(*tasks, **extra) -> dict:
    """An import payload with the envelope filled in."""
    body = {"kind": TRANSFER_KIND, "version": TRANSFER_VERSION, "tasks": list(tasks)}
    body.update(extra)
    return body


# =========================================================================
# export
# =========================================================================


class TestExport:
    @pytest.mark.asyncio
    async def test_export_carries_the_task_and_its_provenance(self, client):
        await make_task()

        res = await client.get("/campus/export")

        assert res.status_code == 200
        body = res.json()
        assert body["kind"] == TRANSFER_KIND
        assert body["version"] == TRANSFER_VERSION
        assert body["count"] == 1
        assert body["umos"] == [UMO]

        row = body["tasks"][0]
        assert row["title"] == "提交软件工程实验三报告"
        assert row["task_type"] == "homework"
        # Provenance is the product's answer to "did the AI make this up". A task
        # that arrived without it would be an unexplainable card on the far board.
        assert row["raw_text"] == "实验三报告周五晚上12点前提交"
        assert row["extract_reason"] == "包含截止关键词与明确时间"
        assert row["source_sender_name"] == "张老师"

    @pytest.mark.asyncio
    async def test_export_covers_every_group_by_default(self, client):
        await make_task(title="任务甲")
        await make_task(umo=OTHER_UMO, title="任务乙")

        body = (await client.get("/campus/export")).json()

        # The board's other endpoints default to one group. Here that default
        # would be a backup that quietly lost the rest.
        assert body["count"] == 2
        assert body["umos"] == sorted([UMO, OTHER_UMO])

    @pytest.mark.asyncio
    async def test_export_can_be_narrowed_to_one_group(self, client):
        await make_task(title="任务甲")
        await make_task(umo=OTHER_UMO, title="任务乙")

        body = (await client.get(f"/campus/export?umo={OTHER_UMO}")).json()

        assert [r["title"] for r in body["tasks"]] == ["任务乙"]

    @pytest.mark.asyncio
    async def test_export_includes_finished_tasks_unless_filtered(self, client):
        await make_task(title="做完的", status="done")
        await make_task(title="还没做的", status="active")

        everything = (await client.get("/campus/export")).json()
        assert {r["title"] for r in everything["tasks"]} == {"做完的", "还没做的"}

        narrowed = (await client.get("/campus/export?status=active")).json()
        assert [r["title"] for r in narrowed["tasks"]] == ["还没做的"]

    @pytest.mark.asyncio
    async def test_reminder_job_ids_do_not_travel(self, client):
        """They name rows in *this* machine's cron table.

        Carried over, they would make a task on the far machine claim it is
        scheduled while nothing is going to fire -- the one failure a student
        would only discover after the deadline passed.
        """
        await make_task(reminder_job_ids=["job-1", "job-2"])

        row = (await client.get("/campus/export")).json()["tasks"][0]

        assert "reminder_job_ids" not in row
        assert "reminded_at" not in row

    @pytest.mark.asyncio
    async def test_empty_board_exports_a_valid_empty_document(self, client):
        body = (await client.get("/campus/export")).json()

        assert body["count"] == 0
        assert body["tasks"] == []
        assert body["umos"] == []
        # Still stamped, so importing it back is a no-op rather than an error.
        assert body["kind"] == TRANSFER_KIND


# =========================================================================
# round trip
# =========================================================================


class TestRoundTrip:
    @pytest.mark.asyncio
    async def test_export_then_import_into_another_group_reproduces_the_task(
        self, client
    ):
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await make_task(
            deadline=deadline, location="教一 305", items=["身份证", "校园卡"]
        )

        exported = (await client.get("/campus/export")).json()
        res = await client.post(
            "/campus/import", json=doc(*exported["tasks"], umo=OTHER_UMO)
        )

        assert res.status_code == 200
        report = res.json()
        assert report["created"] == 1
        assert report["skipped"] == 0
        assert report["umos"] == [OTHER_UMO]

        landed = await store.list_tasks(OTHER_UMO, statuses=("active",))
        assert len(landed) == 1
        task = landed[0]
        assert task.title == "提交软件工程实验三报告"
        assert task.location == "教一 305"
        assert task.items == ["身份证", "校园卡"]
        # The whole product hinges on the deadline being the same instant on both
        # machines. SQLite hands datetimes back naive, so read it the way every
        # other read path does -- if the file had carried local time instead of
        # UTC this would be off by eight hours in China.
        assert as_utc(task.deadline) == deadline

    @pytest.mark.asyncio
    async def test_retargeting_recomputes_the_dedup_key(self, client):
        """Otherwise the arriving task carries a key derived from the old group,
        and the next extraction of the same notice would not recognise it."""
        await make_task()
        exported = (await client.get("/campus/export")).json()

        await client.post("/campus/import", json=doc(*exported["tasks"], umo=OTHER_UMO))

        landed = (await store.list_tasks(OTHER_UMO, statuses=("active",)))[0]
        assert landed.dedup_key == store.dedup_key(
            OTHER_UMO, landed.title, landed.deadline
        )

    @pytest.mark.asyncio
    async def test_tasks_without_a_umo_land_on_the_default_board(self, client):
        res = await client.post("/campus/import", json=doc({"title": "手写的任务"}))

        assert res.json()["created"] == 1
        landed = await store.list_tasks(UMO, statuses=("active",))
        assert [t.title for t in landed] == ["手写的任务"]

    @pytest.mark.asyncio
    async def test_a_hand_written_row_needs_only_a_title(self, client):
        res = await client.post(
            "/campus/import",
            json=doc({"title": "交体育免修申请"}),
        )

        assert res.status_code == 200, res.text
        task = (await store.list_tasks(UMO, statuses=("active",)))[0]
        assert task.task_type == "notice"
        assert task.status == "active"
        assert task.deadline is None
        assert task.task_id  # generated, not required from the file

    @pytest.mark.asyncio
    async def test_created_at_survives_so_ordering_does(self, client):
        old = datetime(2026, 3, 1, 2, 0, tzinfo=timezone.utc)
        res = await client.post(
            "/campus/import",
            json=doc({"title": "开学第一周的通知", "created_at": old.isoformat()}),
        )

        assert res.json()["created"] == 1
        task = (await store.list_tasks(UMO, statuses=("active",)))[0]
        # A fresh timestamp would make a semester of imported tasks all look like
        # they arrived at once.
        assert as_utc(task.created_at) == old


# =========================================================================
# importing twice
# =========================================================================


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_importing_the_same_file_twice_changes_nothing(self, client):
        await make_task()
        exported = (await client.get("/campus/export")).json()
        payload = doc(*exported["tasks"], umo=OTHER_UMO)

        first = (await client.post("/campus/import", json=payload)).json()
        second = (await client.post("/campus/import", json=payload)).json()

        assert first["created"] == 1
        assert second == {**second, "created": 0, "skipped": 1}
        assert len(await store.list_tasks(OTHER_UMO, statuses=("active",))) == 1
        assert "已经在这里了" in second["detail"]

    @pytest.mark.asyncio
    async def test_a_task_the_far_machine_extracted_itself_is_not_duplicated(
        self, client
    ):
        """The dedup half of the identity test.

        A student who exports from a laptop and imports onto a desktop that
        watched the same group would otherwise get every task twice, with no way
        to tell which is which.
        """
        deadline = datetime(2026, 8, 14, 15, 59, tzinfo=timezone.utc)
        await make_task(deadline=deadline)

        # Same notice, same group, but extracted independently: a different
        # task_id and no shared history.
        res = await client.post(
            "/campus/import",
            json=doc(
                {
                    "task_id": "id-from-the-other-laptop",
                    "umo": UMO,
                    "title": "提交软件工程实验三报告",
                    "task_type": "homework",
                    "deadline": deadline.isoformat(),
                }
            ),
        )

        assert res.json()["skipped"] == 1
        assert len(await store.list_tasks(UMO, statuses=("active",))) == 1

    @pytest.mark.asyncio
    async def test_the_same_task_twice_inside_one_file_is_caught(self, client):
        row = {"title": "交实验报告", "task_type": "homework"}

        res = await client.post("/campus/import", json=doc(row, dict(row)))

        assert res.json() == {**res.json(), "created": 1, "skipped": 1}

    @pytest.mark.asyncio
    async def test_overwrite_updates_instead_of_skipping(self, client):
        task = await make_task(location=None)
        exported = (await client.get("/campus/export")).json()
        row = dict(exported["tasks"][0])
        row["location"] = "教一 305"
        row["title"] = "提交软件工程实验三报告"

        res = await client.post("/campus/import", json=doc(row, overwrite=True))

        report = res.json()
        assert report["created"] == 0
        assert report["updated"] == 1
        refreshed = await store.get_task(task.task_id)
        assert refreshed is not None
        assert refreshed.location == "教一 305"

    @pytest.mark.asyncio
    async def test_overwrite_keeps_the_rows_own_id(self, client):
        task = await make_task()
        exported = (await client.get("/campus/export")).json()

        await client.post(
            "/campus/import", json=doc(*exported["tasks"], overwrite=True)
        )

        # Updating a task must not orphan the reminders and the trace that point
        # at it by task_id.
        assert await store.get_task(task.task_id) is not None
        assert len(await store.list_tasks(UMO, statuses=("active",))) == 1


# =========================================================================
# refusing bad files
# =========================================================================


class TestRejection:
    @pytest.mark.asyncio
    async def test_a_file_from_another_tool_is_refused(self, client):
        res = await client.post(
            "/campus/import",
            json={"kind": "chrome.bookmarks", "version": 1, "tasks": []},
        )

        assert res.status_code == 422
        assert "课讯" in res.text

    @pytest.mark.asyncio
    async def test_a_newer_format_is_refused_rather_than_half_read(self, client):
        res = await client.post(
            "/campus/import",
            json={
                "kind": TRANSFER_KIND,
                "version": TRANSFER_VERSION + 1,
                "tasks": [{"title": "来自未来的任务"}],
            },
        )

        assert res.status_code == 422
        assert len(await store.list_tasks(UMO, statuses=("active",))) == 0

    @pytest.mark.asyncio
    async def test_an_empty_title_is_refused(self, client):
        res = await client.post("/campus/import", json=doc({"title": "   "}))

        assert res.status_code == 422
        assert "标题" in res.text

    @pytest.mark.asyncio
    async def test_an_unknown_task_type_is_refused_not_relabelled(self, client):
        res = await client.post(
            "/campus/import",
            json=doc({"title": "某件事", "task_type": "chore"}),
        )

        assert res.status_code == 422
        assert len(await store.list_tasks(UMO, statuses=("active",))) == 0

    @pytest.mark.asyncio
    async def test_an_out_of_range_confidence_is_refused(self, client):
        res = await client.post(
            "/campus/import",
            json=doc({"title": "某件事", "confidence": 7}),
        )

        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_an_empty_document_says_so_rather_than_failing(self, client):
        res = await client.post("/campus/import", json=doc())

        assert res.status_code == 200
        assert res.json()["detail"] == "文件里没有任务"


# =========================================================================
# reminders
# =========================================================================


class TestReminders:
    @pytest.mark.asyncio
    async def test_import_replans_reminders_for_what_it_wrote(
        self, client, monkeypatch
    ):
        """The file has no job ids, so the importer must plan from the deadline.

        Skip this and the far machine shows tasks with deadlines and no alarms.
        """
        planned: list[str] = []

        async def fake_schedule(task, **kw):
            planned.append(task.task_id)
            await store.update_task(task.task_id, reminder_job_ids=["job-x"])
            return []

        monkeypatch.setattr(reminders, "schedule_for_task", fake_schedule)

        deadline = datetime.now(timezone.utc) + timedelta(days=2)
        res = await client.post(
            "/campus/import",
            json=doc({"title": "交实验报告", "deadline": deadline.isoformat()}),
        )

        assert res.json()["reminders_planned"] == 1
        assert len(planned) == 1

    @pytest.mark.asyncio
    async def test_a_scheduler_failure_does_not_fail_the_import(
        self, client, monkeypatch
    ):
        """An unscheduled task is degraded; a 500 would lose the whole file."""

        async def boom(task, **kw):
            raise RuntimeError("scheduler down")

        monkeypatch.setattr(reminders, "schedule_for_task", boom)

        res = await client.post("/campus/import", json=doc({"title": "交实验报告"}))

        assert res.status_code == 200
        assert res.json()["created"] == 1
        assert res.json()["reminders_planned"] == 0


# =========================================================================
# the module underneath
# =========================================================================


class TestTransferModule:
    @pytest.mark.asyncio
    async def test_apply_import_reports_which_tasks_it_touched(self, campus_db):
        from campuscue.api.schemas import TaskTransfer

        rows = [TaskTransfer(title="甲"), TaskTransfer(title="乙")]

        report = await transfer.apply_import(rows, default_umo=UMO)

        assert len(report.created) == 2
        assert report.umos == {UMO}
        # Ids, not just counts: the caller has to reschedule exactly these.
        for task_id in report.created:
            assert await store.get_task(task_id) is not None

    def test_transfer_fields_never_include_machine_local_state(self):
        for name in ("id", "task_id", "created_at", "reminder_job_ids", "reminded_at"):
            assert name not in transfer.TRANSFER_FIELDS
