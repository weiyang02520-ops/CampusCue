"""The board's HTTP surface, driven through a real ASGI app.

These go through httpx against a mounted router rather than calling the endpoint
functions directly, because most of what can break here is in the layer the
functions do not see: Pydantic dropping a field that the frontend reads, a query
parameter whose default silently scopes the board to the wrong group, a 404 that
should have been a 400.

Two properties are worth stating up front, because both were bugs waiting to
happen and both are now pinned below:

* ``TaskOut.umo`` must survive serialisation. The SSE stream is one hub for the
  whole process, so the board filters arriving events by umo. Drop the field and
  every event from every group renders on every board.
* ``PATCH`` must only touch what was sent. A frontend that posts the whole task
  back would mark an inferred deadline as student-confirmed and strip the 推断
  badge off a time nobody actually checked.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import notify, reminders, store
from campuscue.api import routes
from campuscue.api.events import hub
from campuscue.api.schemas import short_umo
from campuscue.models import CampusExtraction, CampusSource, CampusTask

UMO = "aiocqhttp:GroupMessage:api-7788"
OTHER_UMO = "aiocqhttp:GroupMessage:api-9900"


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    """A throwaway SQLite file, patched in where the store looks for it.

    Same reasoning as test_campuscue_tools.py: ``store`` binds astrbot's global
    ``db_helper`` at import time, so the patch targets the store's attribute.
    """
    db = SQLiteDatabase(str(tmp_path / "campus-api-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    # The default umo is read from the environment at import time. Pinning it
    # keeps these tests independent of whatever CAMPUSCUE_DEMO_UMO is set to on
    # the machine running them -- which on a demo machine is not the default.
    monkeypatch.setattr(routes, "DEFAULT_UMO", UMO)
    # The scheduler is left unbound; schedule_for_task degrades to a no-op.
    monkeypatch.setattr(reminders, "_cron", None)
    monkeypatch.setattr(reminders, "_ctx", None)

    # The notify endpoints run the real delivery path, and the real path spawns
    # PowerShell. Left alone, running the suite on Windows puts actual desktop
    # notifications on the developer's screen and adds a second per call. The
    # subprocess itself is covered in test_campuscue_notify.py.
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
    }
    defaults.update(kw)
    task = CampusTask(**defaults)
    task.dedup_key = store.dedup_key(task.umo, task.title, task.deadline)
    return await store.create_task(task)


async def make_source(umo: str, **kw) -> CampusSource:
    async with store.db_helper.get_db() as session:
        source = await store.get_or_create_source(session, umo)
        for key, value in kw.items():
            setattr(source, key, value)
        session.add(source)
        await session.commit()
        await session.refresh(source)
        return source


class TestAuth:
    @pytest.mark.asyncio
    async def test_stream_uses_dashboard_auth_when_enabled(self, client, monkeypatch):
        """The event stream carries full task payloads and must not be the one
        CampusCue endpoint left open when the rest of the board requires login.
        """
        from astrbot.dashboard.api import auth

        async def deny(_request):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="login required")

        monkeypatch.setenv("CAMPUSCUE_REQUIRE_AUTH", "1")
        monkeypatch.setattr(auth, "require_dashboard_user", deny)

        response = await client.get("/campus/stream")

        assert response.status_code == 401


# =========================================================================
# label resolution
# =========================================================================


class TestShortUmo:
    def test_a_qq_group_umo_becomes_readable(self):
        assert short_umo("aiocqhttp:GroupMessage:7788") == "QQ群 7788"

    def test_webchat_is_named_too(self):
        assert short_umo("webchat:FriendMessage:abc") == "网页私聊 abc"

    def test_a_private_chat_is_not_called_a_group(self):
        """The notify target is normally a private chat, and calling it 群 would
        tell the student their reminders go somewhere they do not."""
        assert short_umo("qq:FriendMessage:20002") == "QQ私聊 20002"

    def test_an_unknown_platform_keeps_its_own_name(self):
        assert short_umo("telegram:GroupMessage:42") == "telegram 42"

    def test_a_shape_it_does_not_recognise_is_returned_as_is(self):
        """A mislabelled group is worse than an ugly one: the label is what a
        student uses to decide whose deadlines they are looking at."""
        assert short_umo("weird") == "weird"
        assert short_umo("a:b") == "a:b"


# =========================================================================
# sources
# =========================================================================


class TestSources:
    @pytest.mark.asyncio
    async def test_the_default_group_is_listed_even_with_no_row(self, client):
        """On a fresh install nothing has been seen yet, but the board still has
        to be able to preselect the group it is showing."""
        res = await client.get("/campus/sources")

        assert res.status_code == 200
        assert [s["umo"] for s in res.json()] == [UMO]
        assert res.json()[0]["label"] == "QQ群 api-7788"

    @pytest.mark.asyncio
    async def test_display_name_wins_over_course_name(self, client):
        await make_source(UMO, display_name="软工三班", course_name="软件工程")

        (source,) = (await client.get("/campus/sources")).json()

        assert source["label"] == "软工三班"
        assert source["course_name"] == "软件工程"

    @pytest.mark.asyncio
    async def test_course_name_is_used_when_there_is_no_display_name(self, client):
        await make_source(UMO, course_name="软件工程")

        (source,) = (await client.get("/campus/sources")).json()

        assert source["label"] == "软件工程"

    @pytest.mark.asyncio
    async def test_busiest_group_comes_first(self, client):
        """So a real course group outranks one the demo touched once."""
        await make_source(UMO, stat_seen=3)
        await make_source(OTHER_UMO, stat_seen=140)

        order = [s["umo"] for s in (await client.get("/campus/sources")).json()]

        assert order == [OTHER_UMO, UMO]

    @pytest.mark.asyncio
    async def test_open_task_counts_are_per_group(self, client):
        await make_source(UMO, stat_seen=10)
        await make_source(OTHER_UMO, stat_seen=5)
        await make_task(title="甲")
        await make_task(title="乙", status="pending_confirm")
        await make_task(title="丙", umo=OTHER_UMO)

        counts = {
            s["umo"]: s["open_tasks"]
            for s in (await client.get("/campus/sources")).json()
        }

        assert counts == {UMO: 2, OTHER_UMO: 1}

    @pytest.mark.asyncio
    async def test_finished_tasks_do_not_count(self, client):
        await make_source(UMO, stat_seen=1)
        await make_task(title="做完了", status="done")
        await make_task(title="不是任务", status="dismissed")
        await make_task(title="还没做")

        (source,) = (await client.get("/campus/sources")).json()

        assert source["open_tasks"] == 1

    @pytest.mark.asyncio
    async def test_a_group_known_only_from_a_task_still_appears(self, client):
        """A hand-created task can name a group that was never observed. The task
        exists, so the student has to be able to navigate to it."""
        await make_task(umo=OTHER_UMO, source_kind="manual")

        listed = {s["umo"]: s for s in (await client.get("/campus/sources")).json()}

        assert set(listed) == {UMO, OTHER_UMO}
        assert listed[OTHER_UMO]["open_tasks"] == 1
        assert listed[OTHER_UMO]["messages_seen"] == 0

    @pytest.mark.asyncio
    async def test_no_group_is_listed_twice(self, client):
        """The default umo is appended when missing; it must not be appended when
        it is already there."""
        await make_source(UMO, stat_seen=2)
        await make_task()

        umos = [s["umo"] for s in (await client.get("/campus/sources")).json()]

        assert len(umos) == len(set(umos)) == 1

    @pytest.mark.asyncio
    async def test_message_counters_are_reported(self, client):
        await make_source(UMO, stat_seen=204)

        (source,) = (await client.get("/campus/sources")).json()

        assert source["messages_seen"] == 204

    @pytest.mark.asyncio
    async def test_the_demo_group_disappears_once_a_real_one_is_watched(self, client):
        """The default umo is a fresh-install placeholder, not a group. Appending
        it unconditionally made the sample groups from a demo come back into the
        picker after they were deleted, with no way to get rid of them: delete
        cannot remove a row that was never written."""
        await make_source(OTHER_UMO, stat_seen=12)

        umos = [s["umo"] for s in (await client.get("/campus/sources")).json()]

        assert umos == [OTHER_UMO]
        assert UMO not in umos

    @pytest.mark.asyncio
    async def test_the_board_falls_back_to_a_watched_group(self, client):
        """/default-source has to agree with /sources: a board pointed at a session
        the picker does not list shows one group and names another."""
        await make_source(OTHER_UMO, stat_seen=12)

        fallback = (await client.get("/campus/default-source")).json()

        assert fallback["umo"] == OTHER_UMO

    @pytest.mark.asyncio
    async def test_the_default_is_still_the_fallback_with_no_groups_at_all(
        self, client
    ):
        fallback = (await client.get("/campus/default-source")).json()

        assert fallback["umo"] == UMO


class TestDefaultSource:
    @pytest.mark.asyncio
    async def test_it_answers_before_anything_has_been_seen(self, client):
        res = await client.get("/campus/default-source")

        assert res.status_code == 200
        assert res.json()["umo"] == UMO
        assert res.json()["label"] == "QQ群 api-7788"

    @pytest.mark.asyncio
    async def test_it_uses_the_stored_row_once_there_is_one(self, client):
        await make_source(UMO, display_name="软工三班", stat_seen=12)
        await make_task()

        body = (await client.get("/campus/default-source")).json()

        assert body["label"] == "软工三班"
        assert body["messages_seen"] == 12
        assert body["open_tasks"] == 1

    @pytest.mark.asyncio
    async def test_it_is_not_confused_by_a_busier_other_group(self, client):
        """list_sources orders by traffic; the default must still be the one
        returned, or the board opens on a group the student did not choose."""
        await make_source(OTHER_UMO, stat_seen=900, display_name="别人的群")
        await make_source(UMO, stat_seen=1, display_name="我的群")

        assert (await client.get("/campus/default-source")).json()["label"] == "我的群"


# =========================================================================
# task listing and scoping
# =========================================================================


class TestTaskScoping:
    @pytest.mark.asyncio
    async def test_a_task_carries_its_group_on_the_wire(self, client):
        """Without this the SSE filter cannot tell whose event just arrived."""
        await make_task()

        (task,) = (await client.get("/campus/tasks")).json()

        assert task["umo"] == UMO

    @pytest.mark.asyncio
    async def test_listing_defaults_to_the_default_group(self, client):
        await make_task(title="我的")
        await make_task(title="别人的", umo=OTHER_UMO)

        titles = [t["title"] for t in (await client.get("/campus/tasks")).json()]

        assert titles == ["我的"]

    @pytest.mark.asyncio
    async def test_an_explicit_umo_switches_boards(self, client):
        await make_task(title="我的")
        await make_task(title="别人的", umo=OTHER_UMO)

        res = await client.get("/campus/tasks", params={"umo": OTHER_UMO})

        assert [t["title"] for t in res.json()] == ["别人的"]

    @pytest.mark.asyncio
    async def test_stats_are_scoped_too(self, client):
        await make_source(UMO, stat_seen=100, stat_l1_passed=10)
        await make_source(OTHER_UMO, stat_seen=4, stat_l1_passed=4)
        await make_task(title="我的")
        await make_task(title="别人的一", umo=OTHER_UMO)
        await make_task(title="别人的二", umo=OTHER_UMO)

        mine = (await client.get("/campus/stats")).json()
        theirs = (await client.get("/campus/stats", params={"umo": OTHER_UMO})).json()

        assert (mine["total_active"], theirs["total_active"]) == (1, 2)
        assert mine["messages_seen"] == 100
        assert mine["l1_filtered_ratio"] == 0.9


# =========================================================================
# hand-created tasks -- the board's 新建 button
# =========================================================================


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_creating_a_task_by_hand(self, client):
        res = await client.post(
            "/campus/tasks",
            json={"title": "交实验报告", "task_type": "homework"},
        )

        assert res.status_code == 200
        body = res.json()
        assert body["title"] == "交实验报告"
        assert body["source_kind"] == "manual"
        assert body["status"] == "active"

    @pytest.mark.asyncio
    async def test_creating_the_same_task_twice_is_rejected(self, client):
        """The board's 新建 must not create two tasks for one obligation. The LLM
        tool path dedups (campuscue/tools.py); the API path must too, or a fast
        double-click or a repeated entry produces twin cards and twin reminders.
        """
        first = await client.post(
            "/campus/tasks",
            json={"title": "周五交实验三", "task_type": "homework"},
        )
        assert first.status_code == 200

        second = await client.post(
            "/campus/tasks",
            json={"title": "周五交实验三", "task_type": "homework"},
        )
        assert second.status_code == 409
        assert "已存在" in second.json()["detail"]

        matches = [
            t for t in (await client.get("/campus/tasks")).json()
            if t["title"] == "周五交实验三"
        ]
        assert len(matches) == 1

    @pytest.mark.asyncio
    async def test_same_title_with_different_deadline_is_not_a_duplicate(
        self, client
    ):
        """Moving a deadline is announcing a different obligation (same rule as
        dedup_key): the second entry must be allowed, not swallowed."""
        await client.post(
            "/campus/tasks",
            json={"title": "实验三", "deadline": "2026-08-10T23:59:00+08:00"},
        )
        res = await client.post(
            "/campus/tasks",
            json={"title": "实验三", "deadline": "2026-08-17T23:59:00+08:00"},
        )

        assert res.status_code == 200

    @pytest.mark.asyncio
    async def test_same_title_in_a_different_group_is_not_a_duplicate(
        self, client
    ):
        await client.post(
            "/campus/tasks", json={"title": "课程设计"}
        )
        res = await client.post(
            "/campus/tasks",
            params={"umo": OTHER_UMO},
            json={"title": "课程设计"},
        )

        assert res.status_code == 200


# =========================================================================
# editing -- the other half of the answer to "what if the AI is wrong"
# =========================================================================


class TestUpdateTask:
    @pytest.mark.asyncio
    async def test_the_title_can_be_corrected(self, client):
        task = await make_task(title="交实验")

        res = await client.patch(
            f"/campus/tasks/{task.task_id}", json={"title": "提交软件工程实验三报告"}
        )

        assert res.status_code == 200
        assert res.json()["title"] == "提交软件工程实验三报告"
        assert (await store.get_task(task.task_id)).title == "提交软件工程实验三报告"

    @pytest.mark.asyncio
    async def test_a_hand_set_deadline_is_marked_explicit(self, client):
        """The 推断 badge has to come off a time the student typed themselves."""
        task = await make_task(deadline_is_explicit=False)

        res = await client.patch(
            f"/campus/tasks/{task.task_id}",
            json={"deadline": "2026-12-14T23:59:00+08:00"},
        )

        assert res.json()["deadline_is_explicit"] is True

    @pytest.mark.asyncio
    async def test_editing_something_else_leaves_an_inferred_time_inferred(
        self, client
    ):
        """The reason the frontend sends only changed fields. A whole-object PATCH
        would confirm a deadline nobody looked at."""
        task = await make_task(deadline_is_explicit=False)

        res = await client.patch(
            f"/campus/tasks/{task.task_id}", json={"location": "一教 305"}
        )

        assert res.json()["deadline_is_explicit"] is False
        assert res.json()["location"] == "一教 305"

    @pytest.mark.asyncio
    async def test_the_deadline_is_stored_in_utc(self, client):
        """23:59 Beijing is 15:59 UTC. Getting this wrong moves a deadline most of
        a day while still looking plausible."""
        task = await make_task()

        await client.patch(
            f"/campus/tasks/{task.task_id}",
            json={"deadline": "2026-12-14T23:59:00+08:00"},
        )

        stored = (await store.get_task(task.task_id)).deadline
        assert (stored.hour, stored.minute) == (15, 59)
        assert stored.day == 14

    @pytest.mark.asyncio
    async def test_a_corrected_deadline_re_derives_the_dedup_key(self, client):
        """Otherwise the original notice re-creates the task that was just
        edited, and the correction appears to have been ignored."""
        task = await make_task()
        before = task.dedup_key

        await client.patch(
            f"/campus/tasks/{task.task_id}",
            json={"deadline": "2026-12-14T23:59:00+08:00"},
        )

        assert (await store.get_task(task.task_id)).dedup_key != before

    @pytest.mark.asyncio
    async def test_the_deadline_can_be_cleared(self, client):
        task = await make_task()

        res = await client.patch(
            f"/campus/tasks/{task.task_id}", json={"deadline": None}
        )

        assert res.json()["deadline"] is None

    @pytest.mark.asyncio
    async def test_items_replace_rather_than_append(self, client):
        task = await make_task(items=["学生证"])

        res = await client.patch(
            f"/campus/tasks/{task.task_id}", json={"items": ["计算器", "身份证"]}
        )

        assert res.json()["items"] == ["计算器", "身份证"]

    @pytest.mark.asyncio
    async def test_an_empty_body_is_rejected_rather_than_a_no_op_write(self, client):
        task = await make_task()

        res = await client.patch(f"/campus/tasks/{task.task_id}", json={})

        assert res.status_code == 400

    @pytest.mark.asyncio
    async def test_an_unknown_task_is_a_404(self, client):
        res = await client.patch("/campus/tasks/nope", json={"title": "x"})

        assert res.status_code == 404

    @pytest.mark.asyncio
    async def test_the_edit_is_broadcast_so_other_boards_follow(self, client):
        task = await make_task()
        queue = hub.subscribe()
        try:
            await client.patch(
                f"/campus/tasks/{task.task_id}", json={"title": "改过的标题"}
            )
            payload = json.loads(queue.get_nowait())
        finally:
            hub.unsubscribe(queue)

        assert payload["event"] == "task_updated"
        assert payload["data"]["title"] == "改过的标题"
        assert payload["data"]["umo"] == UMO, (
            "the board filters events by umo; an event without one lands on every "
            "board regardless of which group it came from"
        )


# =========================================================================
# reminders
# =========================================================================


class TestReminders:
    @pytest.mark.asyncio
    async def test_an_unbound_scheduler_reports_nothing_rather_than_guessing(
        self, client
    ):
        """The point of this endpoint is proving the alarms exist. With no
        scheduler the honest answer is an empty list, not a list of what would
        have been scheduled."""
        await make_task()

        res = await client.get("/campus/reminders")

        assert res.status_code == 200
        assert res.json() == []

    @pytest.mark.asyncio
    async def test_it_reads_the_cron_table_and_joins_back_to_tasks(
        self, client, monkeypatch
    ):
        from types import SimpleNamespace

        task = await make_task()
        fire_at = datetime.now(timezone.utc) + timedelta(days=2)
        jobs = [
            SimpleNamespace(
                job_id="job-1",
                name=f"{reminders.JOB_NAME_PREFIX}:{task.task_id}:1440",
                payload={"task_id": task.task_id, "label": "提前 1 天"},
                next_run_time=fire_at,
                status="scheduled",
            ),
            # Someone else's cron job, in the same table.
            SimpleNamespace(
                job_id="job-2",
                name="daily-standup",
                payload={},
                next_run_time=fire_at,
                status="scheduled",
            ),
        ]

        async def list_jobs(kind):  # noqa: ARG001
            return jobs

        monkeypatch.setattr(reminders, "_cron", SimpleNamespace(list_jobs=list_jobs))
        monkeypatch.setattr(reminders, "_ctx", object())

        body = (await client.get("/campus/reminders")).json()

        assert [r["job_id"] for r in body] == ["job-1"]
        assert body[0]["task_title"] == task.title
        assert body[0]["label"] == "提前 1 天"

    @pytest.mark.asyncio
    async def test_reminders_for_another_group_are_not_listed(
        self, client, monkeypatch
    ):
        from types import SimpleNamespace

        other = await make_task(umo=OTHER_UMO)

        async def list_jobs(kind):  # noqa: ARG001
            return [
                SimpleNamespace(
                    job_id="job-1",
                    name=f"{reminders.JOB_NAME_PREFIX}:{other.task_id}:1440",
                    payload={"task_id": other.task_id, "label": "提前 1 天"},
                    next_run_time=datetime.now(timezone.utc),
                    status="scheduled",
                )
            ]

        monkeypatch.setattr(reminders, "_cron", SimpleNamespace(list_jobs=list_jobs))
        monkeypatch.setattr(reminders, "_ctx", object())

        assert (await client.get("/campus/reminders")).json() == []
        scoped = await client.get("/campus/reminders", params={"umo": OTHER_UMO})
        assert [r["task_id"] for r in scoped.json()] == [other.task_id]


class TestRemindNow:
    @pytest.mark.asyncio
    async def test_the_preview_is_returned_even_with_nothing_to_push_to(self, client):
        """Setup and rehearsal both need to see the text before a platform is
        attached, so an unbound scheduler is a 200 with delivered=False."""
        task = await make_task()

        res = await client.post(f"/campus/tasks/{task.task_id}/remind-now")

        assert res.status_code == 200
        assert res.json()["delivered"] is False
        assert task.title in res.json()["preview"]
        assert res.json()["detail"] == "调度器未就绪"

    @pytest.mark.asyncio
    async def test_a_failing_platform_is_reported_not_raised(self, client, monkeypatch):
        from types import SimpleNamespace

        task = await make_task()

        async def send_message(umo, chain):  # noqa: ARG001
            raise RuntimeError("napcat 没连上")

        monkeypatch.setattr(reminders, "_cron", object())
        monkeypatch.setattr(
            reminders, "_ctx", SimpleNamespace(send_message=send_message)
        )

        res = await client.post(f"/campus/tasks/{task.task_id}/remind-now")

        assert res.status_code == 200
        assert res.json()["delivered"] is False
        assert "napcat 没连上" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_a_successful_push_goes_to_the_task_s_own_group(
        self, client, monkeypatch
    ):
        from types import SimpleNamespace

        task = await make_task(umo=OTHER_UMO)
        sent: list[str] = []

        async def send_message(umo, chain):  # noqa: ARG001
            sent.append(umo)
            return True

        monkeypatch.setattr(reminders, "_cron", object())
        monkeypatch.setattr(
            reminders, "_ctx", SimpleNamespace(send_message=send_message)
        )

        res = await client.post(f"/campus/tasks/{task.task_id}/remind-now")

        assert res.json()["delivered"] is True
        assert sent == [OTHER_UMO]

    @pytest.mark.asyncio
    async def test_an_unknown_task_is_a_404(self, client):
        assert (await client.post("/campus/tasks/nope/remind-now")).status_code == 404


# =========================================================================
# maintaining what a group is
# =========================================================================


class TestPatchSource:
    """Naming a group is the one edit that changes future accuracy rather than
    only correcting the past: ``build_user_message`` renders course_name as
    对应课程 in the L2 prompt."""

    @pytest.mark.asyncio
    async def test_naming_a_course_persists_and_is_returned(self, client):
        await make_source(UMO, stat_seen=12)

        res = await client.patch(
            f"/campus/sources/{UMO}", json={"course_name": "软件工程"}
        )

        assert res.status_code == 200
        assert res.json()["course_name"] == "软件工程"
        assert (await store.get_source(UMO)).course_name == "软件工程"

    @pytest.mark.asyncio
    async def test_the_label_falls_back_to_the_course_name(self, client):
        await make_source(UMO)

        res = await client.patch(
            f"/campus/sources/{UMO}", json={"course_name": "数据结构"}
        )

        assert res.json()["label"] == "数据结构"

    @pytest.mark.asyncio
    async def test_a_display_name_outranks_the_course_name(self, client):
        await make_source(UMO, course_name="软件工程")

        res = await client.patch(
            f"/campus/sources/{UMO}", json={"display_name": "软工 2班"}
        )

        assert res.json()["label"] == "软工 2班"
        assert res.json()["course_name"] == "软件工程"

    @pytest.mark.asyncio
    async def test_clearing_a_name_restores_the_readable_umo(self, client):
        """An empty string means "clear this", not "an empty label": the label
        chain only falls through to short_umo() on None."""
        await make_source(UMO, display_name="随手起的名字")

        res = await client.patch(f"/campus/sources/{UMO}", json={"display_name": "  "})

        assert res.json()["label"] == short_umo(UMO)
        assert (await store.get_source(UMO)).display_name is None

    @pytest.mark.asyncio
    async def test_a_group_with_no_row_yet_can_still_be_named(self, client):
        """On a fresh install the picker offers the default umo before anyone has
        spoken in it. Telling CampusCue what it is must not 404."""
        assert await store.get_source(OTHER_UMO) is None

        res = await client.patch(
            f"/campus/sources/{OTHER_UMO}", json={"course_name": "编译原理"}
        )

        assert res.status_code == 200
        assert (await store.get_source(OTHER_UMO)).course_name == "编译原理"

    @pytest.mark.asyncio
    async def test_muting_a_group_is_reversible_and_keeps_its_history(self, client):
        await make_source(UMO, stat_seen=40, course_name="软件工程")

        off = await client.patch(f"/campus/sources/{UMO}", json={"enabled": False})
        assert off.json()["enabled"] is False
        assert off.json()["messages_seen"] == 40

        on = await client.patch(f"/campus/sources/{UMO}", json={"enabled": True})
        assert on.json()["enabled"] is True
        assert on.json()["course_name"] == "软件工程"

    @pytest.mark.asyncio
    async def test_open_task_count_comes_back_with_the_patch(self, client):
        await make_task()
        await make_task(title="第二个任务")

        res = await client.patch(f"/campus/sources/{UMO}", json={"course_name": "软工"})

        assert res.json()["open_tasks"] == 2

    @pytest.mark.asyncio
    async def test_an_unknown_source_type_is_rejected(self, client):
        res = await client.patch(
            f"/campus/sources/{UMO}", json={"source_type": "whatever"}
        )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_an_empty_patch_is_a_400_not_a_silent_success(self, client):
        assert (
            await client.patch(f"/campus/sources/{UMO}", json={})
        ).status_code == 400

    @pytest.mark.asyncio
    async def test_the_colons_in_a_umo_survive_the_path(self, client):
        """The default path converter would truncate at the first colon and patch
        a different group entirely."""
        res = await client.patch(
            f"/campus/sources/{UMO}", json={"course_name": "操作系统"}
        )

        assert res.json()["umo"] == UMO
        assert (await store.get_source(UMO)).course_name == "操作系统"

    @pytest.mark.asyncio
    async def test_the_edit_is_pushed_to_open_boards(self, client):
        queue = hub.subscribe()
        try:
            await client.patch(f"/campus/sources/{UMO}", json={"course_name": "软工"})
            payload = json.loads(queue.get_nowait())
        finally:
            hub.unsubscribe(queue)

        assert payload["event"] == "source_updated"
        assert payload["data"]["course_name"] == "软工"


class TestDeleteSource:
    """Removing a group for real, not disabling it.

    This is the only true delete in the product, and it exists because a
    development database accumulates fixture groups whose traffic counters make
    every number on the board -- the L1 filter ratio above all -- meaningless.
    Unlike a dismissed task there is nothing worth keeping: a fake group has no
    history, and leaving a disabled row behind would keep it in the picker
    forever.
    """

    @pytest.mark.asyncio
    async def test_it_removes_the_group_and_its_tasks(self, client):
        await make_source(OTHER_UMO, display_name="假的群")
        await make_task(umo=OTHER_UMO, title="假任务一")
        await make_task(umo=OTHER_UMO, title="假任务二")

        res = await client.delete(f"/campus/sources/{OTHER_UMO}")

        assert res.status_code == 200
        assert res.json()["tasks"] == 2
        assert await store.get_source(OTHER_UMO) is None
        assert await store.list_tasks(OTHER_UMO) == []

    @pytest.mark.asyncio
    async def test_it_counts_tasks_not_reminders(self, client):
        """The count came from the deleted job ids once, which reported 0 for a
        task that never had a reminder -- i.e. every task on a machine with no
        scheduler bound, which is every test and every replay session."""
        await make_source(OTHER_UMO)
        await make_task(umo=OTHER_UMO, title="没有提醒的任务", reminder_job_ids=[])

        res = await client.delete(f"/campus/sources/{OTHER_UMO}")

        assert res.json()["tasks"] == 1

    @pytest.mark.asyncio
    async def test_another_groups_tasks_are_untouched(self, client):
        """The one property that makes this button safe to press."""
        await make_source(OTHER_UMO)
        await make_task(umo=OTHER_UMO, title="假任务")
        kept = await make_task(title="真任务")

        await client.delete(f"/campus/sources/{OTHER_UMO}")

        assert [t.task_id for t in await store.list_tasks(UMO)] == [kept.task_id]

    @pytest.mark.asyncio
    async def test_the_extraction_audit_goes_with_it(self, client):
        """Leaving the trace rows behind would keep the fake group's messages in
        the 抽取记录 view with no group to attribute them to."""
        await make_source(OTHER_UMO)
        await store.record_extraction(
            CampusExtraction(
                umo=OTHER_UMO, raw_text="假消息", outcome="model_said_none"
            )
        )

        res = await client.delete(f"/campus/sources/{OTHER_UMO}")

        assert res.json()["extractions"] == 1
        assert (await client.get(f"/campus/extractions?umo={OTHER_UMO}")).json() == []

    @pytest.mark.asyncio
    async def test_the_history_can_be_kept(self, client):
        """``with_tasks=false`` unwatches a group without discarding what was
        already extracted from it -- a real group the student is done with, rather
        than a fixture."""
        await make_source(OTHER_UMO)
        await make_task(umo=OTHER_UMO, title="真的任务")

        res = await client.delete(f"/campus/sources/{OTHER_UMO}?with_tasks=false")

        assert res.json()["tasks"] == 0
        assert await store.get_source(OTHER_UMO) is None
        assert len(await store.list_tasks(OTHER_UMO)) == 1

    @pytest.mark.asyncio
    async def test_deleting_a_group_that_was_never_there_is_not_an_error(self, client):
        """Idempotent on purpose: the picker and the database can disagree, and a
        404 on a second click would look like the first one failed."""
        res = await client.delete("/campus/sources/qq:GroupMessage:never-existed")

        assert res.status_code == 200
        assert res.json()["tasks"] == 0

    @pytest.mark.asyncio
    async def test_open_boards_are_told(self, client):
        await make_source(OTHER_UMO)
        queue = hub.subscribe()
        try:
            await client.delete(f"/campus/sources/{OTHER_UMO}")
            payload = json.loads(queue.get_nowait())
        finally:
            hub.unsubscribe(queue)

        assert payload["event"] == "source_deleted"
        assert payload["data"]["umo"] == OTHER_UMO


# =========================================================================
# notification delivery
# =========================================================================


class TestNotify:
    """Where detections go. One global setting, because there is one student.

    The behaviour itself is pinned in test_campuscue_notify.py; these cover the
    parts only the HTTP layer can get wrong -- a target that saves but could never
    deliver, and a switch that appears to work and changes nothing.
    """

    @pytest.mark.asyncio
    async def test_the_defaults_come_back_before_anything_is_saved(self, client):
        body = (await client.get("/campus/notify")).json()

        assert body["target_umo"] == ""
        assert body["on_detect"] is True
        assert body["deadline_reminders"] is True

    @pytest.mark.asyncio
    async def test_the_picker_offers_the_watched_groups(self, client):
        await make_source(UMO, display_name="软件工程课程群")

        body = (await client.get("/campus/notify")).json()

        assert UMO in [c["umo"] for c in body["candidates"]]

    @pytest.mark.asyncio
    async def test_a_private_chat_is_addressable_by_prefix(self, client):
        """The only uin this process knows is the bot's own, so a private chat
        cannot be enumerated -- the panel builds the umo from a QQ number the
        student types onto this prefix."""
        body = (await client.get("/campus/notify")).json()

        assert body["friend_umo_prefix"].endswith(":FriendMessage:")

    @pytest.mark.asyncio
    async def test_saving_a_target_survives_a_reread(self, client):
        target = "qq:FriendMessage:20002"

        res = await client.patch("/campus/notify", json={"target_umo": target})

        assert res.status_code == 200
        assert res.json()["target_label"] == "QQ私聊 20002"
        assert (await client.get("/campus/notify")).json()["target_umo"] == target

    @pytest.mark.asyncio
    async def test_the_current_setting_stays_in_the_picker(self, client):
        """A saved target whose platform is gone must still be listed: a picker
        that silently drops it looks like the setting reset itself."""
        target = "qq:FriendMessage:20002"
        await client.patch("/campus/notify", json={"target_umo": target})

        body = (await client.get("/campus/notify")).json()

        assert target in [c["umo"] for c in body["candidates"]]

    @pytest.mark.asyncio
    async def test_a_malformed_target_is_rejected_rather_than_saved(self, client):
        """The worst possible outcome here is a setting that saves cleanly and
        then never delivers: the student would believe notifications are on."""
        res = await client.patch("/campus/notify", json={"target_umo": "20002"})

        assert res.status_code == 422
        assert (await client.get("/campus/notify")).json()["target_umo"] == ""

    @pytest.mark.asyncio
    async def test_clearing_the_target_is_allowed(self, client):
        """Empty means "not chosen yet", which is a legitimate state -- delivery
        falls back to the task's own origin."""
        await client.patch("/campus/notify", json={"target_umo": "qq:FriendMessage:1"})

        res = await client.patch("/campus/notify", json={"target_umo": "  "})

        assert res.status_code == 200
        assert res.json()["target_umo"] == ""

    @pytest.mark.asyncio
    async def test_an_empty_patch_is_a_400(self, client):
        assert (await client.patch("/campus/notify", json={})).status_code == 400

    @pytest.mark.asyncio
    async def test_reenabling_deadline_reminders_resyncs(self, client, monkeypatch):
        """schedule_for_task returns early while the switch is off, so every task
        created in the meantime has no alarm. Without the resync, flipping the
        switch back would appear to work and change nothing until a restart."""
        resynced: list[str | None] = []

        async def fake_resync(umo=None):
            resynced.append(umo)

        monkeypatch.setattr(reminders, "resync_all", fake_resync)

        await client.patch("/campus/notify", json={"deadline_reminders": True})

        assert resynced == [None]

    @pytest.mark.asyncio
    async def test_turning_them_off_resyncs_to_cancel_jobs(self, client, monkeypatch):
        """Turning the channel off must reach the cron table, not just the
        setting. ``resync_all`` sweeps every campuscue job first, and
        ``schedule_for_task`` returns early while the switch is off -- so the
        sweep cancels alarms that would otherwise keep firing on a student who
        never touches the task again."""
        resynced: list[str | None] = []

        async def fake_resync(umo=None):
            resynced.append(umo)

        monkeypatch.setattr(reminders, "resync_all", fake_resync)

        await client.patch("/campus/notify", json={"deadline_reminders": False})

        assert resynced == [None]

    @pytest.mark.asyncio
    async def test_a_failing_resync_does_not_lose_the_saved_switch(
        self, client, monkeypatch
    ):
        async def boom(umo=None):
            raise RuntimeError("调度器炸了")

        monkeypatch.setattr(reminders, "resync_all", boom)

        res = await client.patch("/campus/notify", json={"deadline_reminders": True})

        assert res.status_code == 200
        assert res.json()["deadline_reminders"] is True

    @pytest.mark.asyncio
    async def test_the_test_button_returns_the_preview_with_nothing_attached(
        self, client
    ):
        """Same contract as remind-now: the student sees exactly what would be
        sent even when no platform is connected, because that is the state a
        machine is in while it is still being set up."""
        res = await client.post("/campus/notify/test")

        body = res.json()
        assert res.status_code == 200
        assert body["pushed"] is False
        assert "探测到" in body["preview"]
        assert body["detail"]

    @pytest.mark.asyncio
    async def test_the_test_button_goes_through_the_real_path(
        self, client, monkeypatch
    ):
        """A bespoke push would prove nothing about the production one."""
        sent: list[tuple[str, str]] = []

        class Ctx:
            async def send_message(self, umo, chain):
                sent.append((umo, "".join(c.text for c in chain.chain)))
                return True

        monkeypatch.setattr(reminders, "_ctx", Ctx())
        await client.patch(
            "/campus/notify", json={"target_umo": "qq:FriendMessage:20002"}
        )

        body = (await client.post("/campus/notify/test")).json()

        assert body["pushed"] is True
        assert body["toasted"] is True
        assert sent and sent[0][0] == "qq:FriendMessage:20002"

    @pytest.mark.asyncio
    async def test_the_test_button_says_so_when_the_channel_is_off(self, client):
        await client.patch("/campus/notify", json={"on_detect": False})

        body = (await client.post("/campus/notify/test")).json()

        assert body["pushed"] is False
        assert "关闭" in body["detail"]


# =========================================================================
# reminder preferences
# =========================================================================


class TestProfile:
    """The preferences that decide when a reminder fires. Validation lives in the
    schema because the downstream failure is silent: a malformed lead list makes
    ``plan_reminders`` schedule nothing, and a reminder that never fires is the
    one bug this product cannot afford."""

    @pytest.mark.asyncio
    async def test_reading_it_materialises_the_defaults(self, client):
        res = await client.get("/campus/profile")

        assert res.status_code == 200
        body = res.json()
        assert body["umo"] == UMO
        assert body["lead_minutes"]["homework"] == [1440, 120]
        assert body["quiet_hours"] == {"start": "23:00", "end": "07:30"}
        assert body["confidence_threshold"] == 0.7
        assert body["auto_confirm"] is False

    @pytest.mark.asyncio
    async def test_reading_twice_does_not_create_a_second_row(self, client):
        await client.get("/campus/profile")
        await client.get("/campus/profile")

        async with store.db_helper.get_db() as session:
            from sqlmodel import col, select

            from campuscue.models import CampusProfile

            rows = await session.execute(
                select(CampusProfile).where(col(CampusProfile.umo) == UMO)
            )
            assert len(list(rows.scalars().all())) == 1

    @pytest.mark.asyncio
    async def test_changing_a_lead_time_persists(self, client):
        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [2880, 180]}}
        )

        assert res.status_code == 200
        assert res.json()["lead_minutes"]["homework"] == [2880, 180]

        again = await client.get("/campus/profile")
        assert again.json()["lead_minutes"]["homework"] == [2880, 180]

    @pytest.mark.asyncio
    async def test_leads_come_back_earliest_first_and_deduplicated(self, client):
        """The board renders them in this order, and two identical leads would
        push the same sentence twice."""
        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"exam": [120, 2880, 120, 720]}}
        )

        assert res.json()["lead_minutes"]["exam"] == [2880, 720, 120]

    @pytest.mark.asyncio
    async def test_an_unset_field_is_left_alone(self, client):
        await client.patch("/campus/profile", json={"auto_confirm": True})

        res = await client.patch("/campus/profile", json={"confidence_threshold": 0.5})

        assert res.json()["auto_confirm"] is True
        assert res.json()["confidence_threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_a_zero_lead_is_rejected(self, client):
        """A lead of zero fires at the deadline, which is not a reminder."""
        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [0]}}
        )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_a_lead_beyond_two_weeks_is_rejected(self, client):
        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [30000]}}
        )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_an_unknown_task_type_is_rejected(self, client):
        """Silently accepting it would store a key plan_reminders never reads."""
        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"laundry": [60]}}
        )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_quiet_hours_must_be_wall_clock_strings(self, client):
        assert (
            await client.patch(
                "/campus/profile",
                json={"quiet_hours": {"start": "晚上", "end": "07:30"}},
            )
        ).status_code == 422
        assert (
            await client.patch(
                "/campus/profile",
                json={"quiet_hours": {"start": "25:00", "end": "07:30"}},
            )
        ).status_code == 422

    @pytest.mark.asyncio
    async def test_quiet_hours_need_both_ends(self, client):
        res = await client.patch(
            "/campus/profile", json={"quiet_hours": {"start": "23:00"}}
        )
        assert res.status_code == 422

    @pytest.mark.asyncio
    async def test_quiet_hours_may_cross_midnight(self, client):
        """23:00–07:30 is the default and the common case; rejecting a window
        whose end is before its start would reject exactly the one people want."""
        res = await client.patch(
            "/campus/profile", json={"quiet_hours": {"start": "22:30", "end": "08:00"}}
        )

        assert res.status_code == 200
        assert res.json()["quiet_hours"] == {"start": "22:30", "end": "08:00"}

    @pytest.mark.asyncio
    async def test_a_threshold_outside_zero_to_one_is_rejected(self, client):
        assert (
            await client.patch("/campus/profile", json={"confidence_threshold": 1.4})
        ).status_code == 422

    @pytest.mark.asyncio
    async def test_an_empty_patch_is_a_400(self, client):
        assert (await client.patch("/campus/profile", json={})).status_code == 400

    @pytest.mark.asyncio
    async def test_each_group_keeps_its_own_preferences(self, client):
        await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [4320]}}
        )

        other = await client.get(f"/campus/profile?umo={OTHER_UMO}")

        assert other.json()["lead_minutes"]["homework"] == [1440, 120]

    @pytest.mark.asyncio
    async def test_changing_lead_times_resyncs_already_scheduled_reminders(
        self, client, monkeypatch
    ):
        """schedule_for_task reads the profile fresh on every call, so alarms
        already on the scheduler keep their old lead times until something
        re-plans them. Without the resync, saving 提前两天 would appear to work
        and change nothing for any task already on the board."""
        resynced: list[str | None] = []

        async def fake_resync(umo=None):
            resynced.append(umo)

        monkeypatch.setattr(reminders, "resync_all", fake_resync)

        await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [2880]}}
        )

        assert resynced == [UMO]

    @pytest.mark.asyncio
    async def test_a_threshold_change_alone_does_not_resync(self, client, monkeypatch):
        """The threshold decides what becomes a task, not when an existing one
        fires. Rebuilding the whole schedule for it would be pointless work."""
        resynced: list[str | None] = []

        async def fake_resync(umo=None):
            resynced.append(umo)

        monkeypatch.setattr(reminders, "resync_all", fake_resync)

        await client.patch("/campus/profile", json={"confidence_threshold": 0.4})

        assert resynced == []

    @pytest.mark.asyncio
    async def test_a_failing_resync_does_not_lose_the_saved_preference(
        self, client, monkeypatch
    ):
        """Same rationale as _reschedule: an unbound scheduler must not turn a
        saved preference into a 500."""

        async def boom(umo=None):
            raise RuntimeError("调度器炸了")

        monkeypatch.setattr(reminders, "resync_all", boom)

        res = await client.patch(
            "/campus/profile", json={"lead_minutes": {"homework": [2880]}}
        )

        assert res.status_code == 200
        assert (await client.get("/campus/profile")).json()["lead_minutes"][
            "homework"
        ] == [2880]
