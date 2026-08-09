"""Detection-time delivery: what gets said, where it goes, and what cannot break.

The design decisions being pinned here are the two in ``campuscue/notify.py``'s
docstring, and both are product decisions rather than implementation details:

* A detection is announced when it is found, not only before its deadline. A
  lead-time-only design says nothing at all about an undated notice, and says
  nothing on Monday about a Friday deadline it already knew about.
* It goes to one designated session, never back into the group it was read from.
  A bot that talks in a course group of thirty classmates is a bot that gets
  kicked.

The rest is failure containment. ``announce_detection`` runs inside the
extraction pipeline, so every path through it has to end in a report rather than
an exception -- a task that was extracted correctly must not be lost because a
notification could not be delivered.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import notify, store
from campuscue.models import CampusTask

UMO = "qq:GroupMessage:notify-7788"
TARGET = "qq:FriendMessage:20002"


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    """A throwaway database, patched in where the store looks for it."""
    db = SQLiteDatabase(str(tmp_path / "campus-notify-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    try:
        yield db
    finally:
        await db.engine.dispose()


def make_task(**kw) -> CampusTask:
    """An unsaved task -- nothing here needs it persisted."""
    defaults = {
        "umo": UMO,
        "title": "提交软件工程实验三报告",
        "task_type": "homework",
        "status": "active",
        "deadline": datetime(2026, 7, 31, 15, 59, tzinfo=timezone.utc),
        "confidence": 0.9,
        "source_kind": "extracted",
        "source_group_name": "软件工程课程群",
        "source_sender_name": "王老师",
        "raw_text": "实验三报告周五晚上12点前交到教学平台",
    }
    defaults.update(kw)
    return CampusTask(**defaults)


class FakeContext:
    """Stands in for the star context. Records what would have been pushed."""

    def __init__(self, *, delivered: bool = True, blow_up: bool = False):
        self.delivered = delivered
        self.blow_up = blow_up
        self.sent: list[tuple[str, str]] = []

    async def send_message(self, umo, chain):
        if self.blow_up:
            raise RuntimeError("平台掉线了")
        text = "".join(getattr(c, "text", "") for c in chain.chain)
        self.sent.append((umo, text))
        return self.delivered


@pytest.fixture
def bound(monkeypatch):
    """Bind a fake context and stub the toast out.

    The toast is stubbed everywhere below on purpose: spawning PowerShell in a
    unit test would make the suite slow, Windows-only, and would put real
    notifications on the machine running it.
    """
    from campuscue import reminders

    ctx = FakeContext()
    monkeypatch.setattr(reminders, "_ctx", ctx)

    toasts: list[tuple[str, str]] = []

    async def fake_toast(title, body):
        toasts.append((title, body))
        return True

    monkeypatch.setattr(notify, "show_toast", fake_toast)
    return ctx, toasts


# =========================================================================
# settings
# =========================================================================


class TestSettings:
    @pytest.mark.asyncio
    async def test_defaults_apply_before_anything_is_saved(self, campus_db):
        """A fresh install notifies. Requiring setup first would mean the product
        does nothing at all until someone finds the settings panel."""
        settings = await notify.get_settings()

        assert settings.target_umo == ""
        assert settings.on_detect is True
        assert settings.desktop_toast is True
        assert settings.deadline_reminders is True

    @pytest.mark.asyncio
    async def test_saving_one_switch_leaves_the_others_alone(self, campus_db):
        await notify.save_settings(target_umo=TARGET)

        settings = await notify.save_settings(desktop_toast=False)

        assert settings.target_umo == TARGET
        assert settings.desktop_toast is False
        assert settings.on_detect is True

    @pytest.mark.asyncio
    async def test_a_saved_false_survives_the_read(self, campus_db):
        """A falsy value must not be mistaken for "never written" and replaced by
        the default -- that would make every off switch turn itself back on."""
        await notify.save_settings(on_detect=False, deadline_reminders=False)

        settings = await notify.get_settings()

        assert settings.on_detect is False
        assert settings.deadline_reminders is False

    @pytest.mark.asyncio
    async def test_a_missing_table_does_not_stop_extraction(self, monkeypatch):
        """get_settings is called from inside the pipeline. On a database that
        predates campus_settings it has to degrade to the defaults rather than
        raise, or one missing table stops every task being created."""

        async def boom(key, default=None):
            raise RuntimeError("no such table: campus_settings")

        monkeypatch.setattr(store, "get_setting", boom)

        settings = await notify.get_settings()

        assert settings.on_detect is True
        assert settings.target_umo == ""

    @pytest.mark.asyncio
    async def test_the_target_falls_back_to_the_callers_suggestion(self, campus_db):
        """Before a target is designated, delivering to the task's own origin is
        better than going quiet: the settings panel is the fix, not a
        precondition."""
        assert await notify.resolve_target(UMO) == UMO

        await notify.save_settings(target_umo=TARGET)

        assert await notify.resolve_target(UMO) == TARGET


# =========================================================================
# message text
# =========================================================================


class TestComposition:
    def test_it_leads_with_what_happened_not_with_the_title(self):
        """This message arrives unprompted, so the first line has to explain why
        the phone just buzzed."""
        text = notify.compose_detection(make_task())

        first = text.splitlines()[0]
        assert "探测到" in first
        assert "作业" in first

    def test_the_original_message_is_quoted_verbatim(self):
        """The whole trust argument is that the student can see what the model was
        actually looking at."""
        text = notify.compose_detection(make_task())

        assert "实验三报告周五晚上12点前交到教学平台" in text

    def test_a_long_original_is_truncated_rather_than_dropped(self):
        text = notify.compose_detection(make_task(raw_text="通知：" + "细" * 400))

        assert "…" in text
        assert len(text) < 400

    def test_an_inferred_deadline_says_so(self):
        """A time the model guessed must not render identically to one a teacher
        stated."""
        text = notify.compose_detection(make_task(deadline_is_explicit=False))

        assert "推断" in text

    def test_an_undated_task_still_says_something_about_time(self):
        """Silence about the deadline reads as "no deadline", which is a different
        claim from "the notice did not say"."""
        text = notify.compose_detection(make_task(deadline=None))

        assert "没说清" in text

    def test_a_low_confidence_task_tells_the_student_to_check_it(self):
        text = notify.compose_detection(make_task(status="pending_confirm"))

        assert "待确认" in text

    def test_items_and_location_appear_when_present(self):
        text = notify.compose_detection(
            make_task(task_type="exam", location="1教305", items=["身份证", "校园卡"])
        )

        assert "1教305" in text
        assert "身份证" in text
        assert "校园卡" in text

    def test_the_toast_is_two_short_lines(self):
        """A toast is a glance; the detail is in the pushed message."""
        title, body = notify.toast_lines(make_task())

        assert "课讯" in title and "作业" in title
        assert "\n" not in body
        assert "提交软件工程实验三报告" in body


# =========================================================================
# announce_detection
# =========================================================================


class TestAnnounce:
    @pytest.mark.asyncio
    async def test_it_pushes_to_the_designated_target_not_the_source_group(
        self, campus_db, bound
    ):
        """The point of the whole module: 30 classmates must not be told what the
        student's own assistant noticed."""
        ctx, _ = bound
        await notify.save_settings(target_umo=TARGET)

        report = await notify.announce_detection(make_task())

        assert report.pushed is True
        assert report.target == TARGET
        assert [umo for umo, _ in ctx.sent] == [TARGET]
        assert UMO not in [umo for umo, _ in ctx.sent]

    @pytest.mark.asyncio
    async def test_with_no_target_designated_it_falls_back_to_the_origin(
        self, campus_db, bound
    ):
        ctx, _ = bound

        report = await notify.announce_detection(make_task())

        assert report.target == UMO
        assert [umo for umo, _ in ctx.sent] == [UMO]

    @pytest.mark.asyncio
    async def test_the_toast_fires_alongside_the_push(self, campus_db, bound):
        _, toasts = bound

        report = await notify.announce_detection(make_task())

        assert report.toasted is True
        assert len(toasts) == 1

    @pytest.mark.asyncio
    async def test_the_toast_can_be_turned_off_without_losing_the_push(
        self, campus_db, bound
    ):
        ctx, toasts = bound
        await notify.save_settings(desktop_toast=False)

        report = await notify.announce_detection(make_task())

        assert toasts == []
        assert report.toasted is False
        assert report.pushed is True

    @pytest.mark.asyncio
    async def test_the_whole_channel_can_be_turned_off(self, campus_db, bound):
        ctx, toasts = bound
        await notify.save_settings(on_detect=False)

        report = await notify.announce_detection(make_task())

        assert report.skipped == "disabled"
        assert ctx.sent == []
        assert toasts == []

    @pytest.mark.asyncio
    async def test_no_bound_context_is_a_normal_outcome(self, campus_db, monkeypatch):
        """During a replay demo no QQ account is attached, and the board is still
        the real destination. That is a report, not an error."""
        from campuscue import reminders

        monkeypatch.setattr(reminders, "_ctx", None)

        async def fake_toast(title, body):
            return False

        monkeypatch.setattr(notify, "show_toast", fake_toast)

        report = await notify.announce_detection(make_task())

        assert report.skipped == "no_context"
        assert report.pushed is False
        assert report.errors == []

    @pytest.mark.asyncio
    async def test_a_dead_platform_is_reported_not_raised(self, campus_db, monkeypatch):
        """The task is the product, the notification is the courtesy: a push that
        throws must not propagate into the pipeline that just stored the task."""
        from campuscue import reminders

        monkeypatch.setattr(reminders, "_ctx", FakeContext(blow_up=True))

        async def fake_toast(title, body):
            return True

        monkeypatch.setattr(notify, "show_toast", fake_toast)

        report = await notify.announce_detection(make_task())

        assert report.pushed is False
        assert report.errors and "平台掉线了" in report.errors[0]

    @pytest.mark.asyncio
    async def test_an_unmatched_target_reports_rather_than_claiming_success(
        self, campus_db, monkeypatch
    ):
        from campuscue import reminders

        monkeypatch.setattr(reminders, "_ctx", FakeContext(delivered=False))

        async def fake_toast(title, body):
            return True

        monkeypatch.setattr(notify, "show_toast", fake_toast)

        report = await notify.announce_detection(make_task())

        assert report.pushed is False
        assert report.errors == []


# =========================================================================
# the toast subprocess
# =========================================================================


class TestToast:
    def test_the_xml_escapes_the_task_title(self):
        """A title is extracted from a stranger's message. An unescaped ``&`` or
        ``<`` would make LoadXml throw and the notification vanish."""
        xml = notify._toast_xml("课讯 & 你", "第<3>章 & 第4章")

        assert "&amp;" in xml
        assert "&lt;3&gt;" in xml
        assert "<text>" in xml

    def test_it_is_a_no_op_off_windows(self, monkeypatch):
        """The pipeline is not Windows-only even though the toast is."""
        monkeypatch.setattr(notify.os, "name", "posix")

        assert notify._show_toast_blocking("t", "b") is False

    def test_the_payload_travels_in_the_environment_not_on_the_command_line(
        self, monkeypatch
    ):
        """The console codepage on a Chinese Windows install is CP936, and a UTF-8
        argv turns every Chinese character in the title into mojibake before
        PowerShell parses it. Environment variables are handed over as UTF-16."""
        monkeypatch.setattr(notify.os, "name", "nt")
        seen: dict = {}

        class FakeProc:
            returncode = 0
            stdout = b"SHOWN\r\n"
            stderr = b""

        def fake_run(cmd, **kwargs):
            seen["cmd"] = cmd
            seen["env"] = kwargs.get("env") or {}
            seen["input"] = kwargs.get("input")
            return FakeProc()

        monkeypatch.setattr(notify.subprocess, "run", fake_run)

        assert notify._show_toast_blocking(
            "课讯 · 探测到作业信息", "实验三 · 截止 07-31"
        )

        assert "实验三" in seen["env"]["CAMPUSCUE_TOAST_XML"]
        assert not any("实验三" in part for part in seen["cmd"])
        # The script itself arrives on stdin: running it from a file would need
        # -ExecutionPolicy Bypass, and weakening a security control to show a
        # notification is not a trade worth making.
        assert seen["cmd"][-2:] == ["-Command", "-"]
        assert b"ToastNotificationManager" in seen["input"]

    def test_a_nonzero_exit_is_not_reported_as_shown(self, monkeypatch):
        monkeypatch.setattr(notify.os, "name", "nt")

        class FakeProc:
            returncode = 1
            stdout = b""
            stderr = "找不到类型".encode()

        monkeypatch.setattr(notify.subprocess, "run", lambda cmd, **kw: FakeProc())

        assert notify._show_toast_blocking("t", "b") is False

    def test_a_crash_in_the_subprocess_layer_never_escapes(self, monkeypatch):
        monkeypatch.setattr(notify.os, "name", "nt")

        def boom(cmd, **kwargs):
            raise OSError("powershell.exe not found")

        monkeypatch.setattr(notify.subprocess, "run", boom)

        assert notify._show_toast_blocking("t", "b") is False


# =========================================================================
# interaction with deadline reminders
# =========================================================================


class TestDeadlineSwitch:
    @pytest.mark.asyncio
    async def test_lead_time_reminders_can_be_turned_off(self, campus_db, monkeypatch):
        """Detection-time push is now the primary channel, so a student who finds
        a second buzz the day before redundant must be able to drop it without
        losing the detection notice."""
        from campuscue import reminders

        monkeypatch.setattr(reminders, "_cron", None)
        await notify.save_settings(deadline_reminders=False)

        task = CampusTask(
            umo=UMO,
            title="提交实验三报告",
            task_type="homework",
            status="active",
            deadline=datetime.now(timezone.utc) + timedelta(days=3),
            confidence=0.9,
        )

        assert await reminders.schedule_for_task(task) == []
