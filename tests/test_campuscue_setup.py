"""The 接入与自检 page: config writing, QR extraction, and the setup endpoints.

What is worth pinning here is not the HTTP plumbing but the handful of facts that
are silent when wrong. A NapCat config that points at a stale port produces no
error anywhere -- the socket simply never opens. A QR sliced one line short still
renders and simply does not scan. A group resync that adopts every group starts
reading a student's private chats. None of those fail loudly, so each has a test.

The download path is deliberately not exercised: it fetches ~150MB from GitHub.
What is testable about ``install`` -- that the launcher is found whether the zip
is flat or nested -- is covered through ``_shell_root``.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from astrbot.core.db.sqlite import SQLiteDatabase
from campuscue import napcat, reminders, store
from campuscue.api import routes
from campuscue.api import setup as setup_api
from campuscue.models import CampusTask

UMO = "qq:GroupMessage:setup-7788"


# =========================================================================
# config writing
# =========================================================================


def write_config(home, url: str, name: str = "onebot11.json") -> None:
    (home / "config").mkdir(parents=True, exist_ok=True)
    (home / "config" / name).write_text(
        json.dumps(
            {
                "network": {
                    "websocketClients": [
                        {"name": "old", "enable": True, "url": url},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


class TestConfig:
    def test_the_client_dials_out_and_carries_array_segments(self):
        """Two fields with no error path when wrong.

        ``enable`` false means NapCat never dials, and nothing in astrbot's log
        says why -- it is simply waiting. ``messagePostFormat`` other than
        "array" collapses images and @-mentions into CQ codes that
        ``convert_message`` would have to reparse.
        """
        client = napcat.onebot_config("ws://127.0.0.1:6199/ws")["network"][
            "websocketClients"
        ][0]
        assert client["enable"] is True
        assert client["url"] == "ws://127.0.0.1:6199/ws"
        assert client["messagePostFormat"] == "array"

    def test_the_url_is_loopback_not_the_adapters_bind_address(self, monkeypatch):
        """0.0.0.0 is where we listen; it is not an address a client can dial."""
        monkeypatch.setenv("CAMPUSCUE_ONEBOT_PORT", "6199")
        assert napcat.ws_url() == "ws://127.0.0.1:6199/ws"

    def test_apply_config_rewrites_the_template(self, tmp_path):
        write_config(tmp_path, "ws://127.0.0.1:1111/ws")
        written = napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws")
        assert written == ["onebot11.json"]
        assert napcat.is_configured(tmp_path, "ws://127.0.0.1:6199/ws")

    def test_apply_config_also_rewrites_every_per_account_file(self, tmp_path):
        """The failure this prevents, and it is a quiet one: an account that has
        logged in before reads its own ``onebot11_<uin>.json``. Fix only the
        template and re-scanning with the same QQ keeps the old address, with no
        error and no log line -- the bot just never receives anything."""
        write_config(tmp_path, "ws://127.0.0.1:1111/ws")
        write_config(tmp_path, "ws://127.0.0.1:1111/ws", "onebot11_20002.json")

        written = napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws")

        assert sorted(written) == ["onebot11.json", "onebot11_20002.json"]
        assert napcat.is_configured(tmp_path, "ws://127.0.0.1:6199/ws")

    def test_is_configured_is_false_when_only_some_files_match(self, tmp_path):
        """Every, not any: the account whose file is stale connects nowhere, and
        a panel that said 已配置 would be lying about exactly that account."""
        napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws")
        write_config(tmp_path, "ws://127.0.0.1:1111/ws", "onebot11_20002.json")
        assert not napcat.is_configured(tmp_path, "ws://127.0.0.1:6199/ws")

    def test_a_stale_extra_client_is_replaced_not_merged(self, tmp_path):
        """A student who has been trying to fix this by hand leaves half-correct
        clients behind. Merging into that is how NapCat ends up dialling two
        addresses; one known-good client is the intent."""
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "onebot11.json").write_text(
            json.dumps(
                {
                    "network": {
                        "websocketClients": [
                            {"name": "a", "enable": True, "url": "ws://x:1/ws"},
                            {"name": "b", "enable": False, "url": "ws://y:2/ws"},
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws")
        body = json.loads((tmp_path / "config" / "onebot11.json").read_text("utf-8"))
        clients = body["network"]["websocketClients"]
        assert len(clients) == 1
        assert clients[0]["url"] == "ws://127.0.0.1:6199/ws"

    def test_rewriting_an_already_correct_file_writes_nothing(self, tmp_path):
        """So the panel can say 配置已是目标状态 instead of claiming a change."""
        napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws")
        assert napcat.apply_config(tmp_path, "ws://127.0.0.1:6199/ws") == []

    def test_a_corrupt_config_reads_as_unconfigured(self, tmp_path):
        """Hand-edited JSON that no longer parses must show as 未配置 -- which the
        panel can fix with one button -- rather than raising into the status
        endpoint and blanking the whole page."""
        (tmp_path / "config").mkdir(parents=True)
        (tmp_path / "config" / "onebot11.json").write_text("{ not json", "utf-8")
        assert not napcat.is_configured(tmp_path, "ws://127.0.0.1:6199/ws")

    def test_known_accounts_come_from_the_per_account_filenames(self, tmp_path):
        write_config(tmp_path, "ws://a/ws", "onebot11_20002.json")
        write_config(tmp_path, "ws://a/ws", "onebot11_998877.json")
        assert napcat.known_accounts(tmp_path) == ["20002", "998877"]


class TestDiscovery:
    def test_a_directory_with_a_launcher_is_an_install(self, tmp_path, monkeypatch):
        (tmp_path / "launcher.bat").write_text("rem", encoding="utf-8")
        monkeypatch.setenv("CAMPUSCUE_NAPCAT_DIR", str(tmp_path))
        home, launcher = napcat.find_home()
        assert home == tmp_path
        assert launcher is not None and launcher.name == "launcher.bat"

    def test_a_directory_without_one_is_not(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CAMPUSCUE_NAPCAT_DIR", str(tmp_path))
        # Other candidates could match on a machine that has NapCat installed
        # elsewhere, so this asserts on the override only.
        assert napcat._launcher_in(tmp_path) is None

    def test_shell_root_finds_the_launcher_nested_one_level(self, tmp_path):
        """Releases have shipped both flat and inside a single top folder."""
        nested = tmp_path / "NapCat.Shell"
        nested.mkdir()
        (nested / "launcher.bat").write_text("rem", encoding="utf-8")
        assert napcat._shell_root(tmp_path) == nested

    def test_shell_root_finds_a_flat_layout_too(self, tmp_path):
        (tmp_path / "launcher-win10.bat").write_text("rem", encoding="utf-8")
        assert napcat._shell_root(tmp_path) == tmp_path

    def test_the_user_launcher_wins_over_the_admin_one(self, tmp_path):
        """A real install ships all four, and only the -user ones are drivable.

        launcher.bat tests for admin rights and, without them, relaunches itself
        through UAC and exits -- taking our pid and our redirected stdout (and so
        the login QR) with it. Preferring it is the difference between a QR on the
        page and a wait that never ends, and nothing about the filename says so.
        """
        for name in (
            "launcher.bat",
            "launcher-win10.bat",
            "launcher-user.bat",
            "launcher-win10-user.bat",
        ):
            (tmp_path / name).write_text("rem", encoding="utf-8")

        found = napcat._launcher_in(tmp_path)

        assert found is not None and found.name == "launcher-user.bat"


class TestPublish:
    """Moving the unpacked install into place.

    A real install on this machine failed here with ``WinError 5`` and succeeded
    a second later: Defender scans the freshly extracted ``.exe``/``.dll`` files
    and holds the directory while it does. Nothing in the process owns the
    handle, so retrying is the only fix -- and it is the kind of loop a later
    cleanup deletes as pointless, which is why the behaviour is pinned.
    """

    def test_a_directory_locked_for_a_moment_is_retried(self, tmp_path, monkeypatch):
        root, home = tmp_path / "staged", tmp_path / "home"
        root.mkdir()
        monkeypatch.setattr(napcat, "PUBLISH_WAIT", 0)

        calls = {"n": 0}
        real = pathlib.Path.rename

        def flaky(self, target):
            calls["n"] += 1
            if calls["n"] < 3:
                raise PermissionError(5, "拒绝访问")
            return real(self, target)

        monkeypatch.setattr(pathlib.Path, "rename", flaky)
        napcat._publish(root, home)

        assert calls["n"] == 3
        assert home.is_dir()

    def test_a_directory_locked_for_good_is_reported(self, tmp_path, monkeypatch):
        """Not retried forever: something really holding it must surface."""
        root = tmp_path / "staged"
        root.mkdir()
        monkeypatch.setattr(napcat, "PUBLISH_WAIT", 0)
        monkeypatch.setattr(
            pathlib.Path,
            "rename",
            lambda self, target: (_ for _ in ()).throw(PermissionError(5, "拒绝访问")),
        )

        with pytest.raises(napcat.NapCatError, match="杀毒"):
            napcat._publish(root, tmp_path / "home")


# =========================================================================
# the QR
# =========================================================================

QR_BODY = "\n".join(
    [
        "[info] NapCat 启动完成，等待扫码",
        "[info] 二维码已生成，请使用手机 QQ 扫描：",
        *["█▀▀▀▀▀█ ▄▄▀ █▀▀▀▀▀█"] * 12,
        "[info] 等待扫码结果…",
    ]
)


class TestQrcode:
    def test_the_block_drawing_is_pulled_out_of_the_log(self):
        """The panel needs the code alone: the surrounding log lines are long
        enough to force wrapping in a monospace box, and a wrapped QR does not
        scan."""
        block = napcat.qrcode_block(QR_BODY)
        assert block.count("\n") == 11
        assert "info" not in block

    def test_a_log_with_no_qr_yields_nothing(self):
        """So the panel can say 正在等二维码 rather than rendering a stray line as
        a code."""
        assert napcat.qrcode_block("[info] 启动中\n[info] 已连接") == ""

    def test_a_short_run_of_blocks_is_not_treated_as_a_qr(self):
        """Progress bars and box-drawn banners are made of the same characters. A
        real QR is at least 21 modules tall even at half-block density."""
        assert napcat.qrcode_block("█▀▀▀█\n█▄▄▄█") == ""

    def test_the_last_code_wins_when_an_earlier_one_expired(self):
        """Two logins in one session leave two codes in the log; a partially
        scrolled-off older one must not be preferred over the live one."""
        body = "\n".join(["█▀█"] * 9 + ["[info] expired"] + ["█▄█"] * 20)
        assert napcat.qrcode_block(body).count("\n") == 19

    def test_equal_length_reprints_resolve_to_the_newest(self):
        """The bug this replaced, and the reason "longest wins" was not enough.

        NapCat reprints the login code every two minutes as the previous one
        expires, and every reprint is exactly as tall as the last. With a
        strictly-greater comparison the first block kept winning, so the panel
        served a code minutes past its expiry and every scan said 二维码过期 --
        with a perfectly good code sitting further down the same log.
        """
        older, newer = "█▀▀▀▀▀█ ▄▄ █", "█▄▄▄▄▄█ ▀▀ █"
        body = "\n".join(
            ["[warn] 请扫描下面的二维码："]
            + [older] * 18
            + ["[warn] 请扫描下面的二维码："]
            + [newer] * 18
        )
        block = napcat.qrcode_block(body)
        assert older not in block, "the expired reprint must not be what is served"
        assert block == "\n".join([newer] * 18)

    def test_a_short_banner_after_the_code_does_not_displace_it(self):
        """Last-block-wins only holds if short runs are rejected: NapCat draws box
        borders out of the same characters, and one of those below the code would
        otherwise become "the newest QR"."""
        code = "█▀█ ▄▄▀ █▀█"
        body = "\n".join([code] * 18 + ["[info] done"] + ["▀▀▀▀▀"] * 3)
        assert napcat.qrcode_block(body) == "\n".join([code] * 18)

    def test_tail_survives_undecodable_bytes(self, tmp_path, monkeypatch):
        """NapCat writes GBK-ish console output next to the QR's box characters.
        One bad byte must not blank the panel someone is trying to scan."""
        log = tmp_path / "napcat.log"
        log.write_bytes("已连接".encode("gbk") + b"\n\xff\xfe\n" + "█▀█".encode())
        monkeypatch.setattr(napcat, "LOG_PATH", log)
        assert "█▀█" in napcat.tail()


class TestProcess:
    def test_start_refuses_without_an_install(self, tmp_path, monkeypatch):
        monkeypatch.setattr(napcat, "HOME", tmp_path / "nope")
        monkeypatch.setattr(napcat, "find_home", lambda: (None, None))
        with pytest.raises(napcat.NapCatError):
            napcat.start()

    def test_stop_is_a_no_op_when_we_started_nothing(self, monkeypatch):
        """A NapCat the student launched themselves is theirs. Reporting "stopped"
        for a process we never owned would be a lie the panel then acts on."""
        monkeypatch.setattr(napcat, "_proc", None)
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [])
        assert napcat.stop() is False

    def test_status_reports_unconfigured_when_nothing_is_installed(self, monkeypatch):
        monkeypatch.setattr(napcat, "find_home", lambda: (None, None))
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [])
        state = napcat.status()
        assert state.installed is False
        assert state.configured is False
        assert state.detail == "未安装"


class TestOrphanedNapCat:
    """A NapCat that outlived the backend which started it.

    ``_proc`` is module state, so restarting the backend forgets the process
    without ending it. The orphan keeps the inherited log fd and keeps writing
    QR reprints at its own offset, so once a second NapCat joins it, the log
    interleaves two expiring code streams and no scan can ever succeed. Observed
    for real on this machine: two NapCats, seven codes, every scan 二维码过期.
    """

    def test_an_orphan_counts_as_running(self, monkeypatch):
        """Otherwise the page offers 启动 and the click adds a third NapCat."""
        monkeypatch.setattr(napcat, "_proc", None)
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [4242])
        assert napcat.is_running() is True

    def test_status_names_the_orphan_and_says_it_will_be_cleared(self, monkeypatch):
        """运行中 alone leaves no clue why the QR is stale or what to press."""
        monkeypatch.setattr(napcat, "_proc", None)
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [4242])
        monkeypatch.setattr(
            napcat, "find_home", lambda: (napcat.HOME, napcat.HOME / "launcher.bat")
        )
        state = napcat.status()
        assert state.running is True
        assert state.pid == 4242
        assert state.managed is False, (
            "not ours, so 停止 is a sweep not a kill of _proc"
        )
        assert "4242" in state.detail and "重新出码" in state.detail

    def test_starting_clears_orphans_first(self, tmp_path, monkeypatch):
        """The fix proper: one NapCat writing the log, so the newest code is live."""
        home = tmp_path / "napcat"
        home.mkdir()
        (home / "launcher-user.bat").write_text("@echo off\n", encoding="utf-8")
        monkeypatch.setattr(napcat, "HOME", home)
        monkeypatch.setattr(napcat, "LOG_PATH", tmp_path / "napcat.log")
        monkeypatch.setattr(napcat, "_proc", None)
        monkeypatch.setattr(napcat, "find_home", lambda: (home, home / "launcher.bat"))
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [4242, 4243])

        killed: list[int] = []
        monkeypatch.setattr(napcat, "_kill_tree", killed.append)
        monkeypatch.setattr(
            napcat.subprocess,
            "Popen",
            lambda *a, **k: SimpleNamespace(pid=99, poll=lambda: None),
        )

        napcat.start()

        assert killed == [4242, 4243]

    def test_stop_sweeps_an_orphan_even_with_nothing_of_ours(self, monkeypatch):
        """The page says 运行中 for an orphan, so 停止 has to actually stop it."""
        monkeypatch.setattr(napcat, "_proc", None)
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [4242])
        killed: list[int] = []
        monkeypatch.setattr(napcat, "_kill_tree", killed.append)

        assert napcat.stop() is True
        assert killed == [4242]

    def test_only_napcats_from_our_own_install_are_swept(self, monkeypatch):
        """A NapCat the student installed elsewhere and runs themselves is not
        ours to end -- and killing it would take their QQ client down."""
        import psutil

        class FakeProc:
            def __init__(self, pid, exe, name=napcat.BOOT_EXE, created=1.0):
                self.pid = pid
                self.info = {"pid": pid, "name": name, "create_time": created}
                self._exe = exe

            def exe(self):
                return self._exe

            def ppid(self):
                return 1

        ours = str(napcat.HOME)
        monkeypatch.setattr(
            psutil,
            "process_iter",
            lambda attrs=None: [
                FakeProc(1, str(pathlib.Path(ours) / napcat.BOOT_EXE), created=1.0),
                FakeProc(2, r"D:\MyOwnNapCat\NapCatWinBootMain.exe", created=2.0),
                FakeProc(3, str(pathlib.Path(ours) / "QQ.exe"), name="qq.exe"),
            ],
        )
        monkeypatch.setattr(napcat, "_proc", None)

        assert napcat.foreign_pids() == [1]


# =========================================================================
# the endpoints
# =========================================================================


@pytest_asyncio.fixture
async def campus_db(tmp_path, monkeypatch):
    db = SQLiteDatabase(str(tmp_path / "campus-setup-test.db"))
    await db.initialize()
    monkeypatch.setattr(store, "db_helper", db)
    monkeypatch.setattr(routes, "DEFAULT_UMO", UMO)
    monkeypatch.setattr(reminders, "_cron", None)
    monkeypatch.setattr(reminders, "_ctx", None)
    try:
        yield db
    finally:
        await db.engine.dispose()


@pytest_asyncio.fixture
async def client(campus_db):
    app = FastAPI()
    app.include_router(setup_api.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://board") as http:
        yield http


class FakeBot:
    """Enough of aiocqhttp.CQHttp to stand in for a connected NapCat.

    ``_wsr_api_clients`` keyed by self-id is the real signal the page reads: the
    same dict proves the socket is open and says which uin logged in.
    """

    def __init__(self, accounts=(), groups=None, fail=False):
        self._wsr_api_clients = {a: object() for a in accounts}
        self._groups = groups or []
        self._fail = fail
        self.calls: list[str] = []

    async def call_action(self, action, **kw):
        self.calls.append(action)
        if self._fail:
            raise RuntimeError("boom")
        return self._groups


class FakeAdapter:
    def __init__(self, bot):
        self._bot = bot

    def meta(self):
        from types import SimpleNamespace

        return SimpleNamespace(name="aiocqhttp")

    def get_client(self):
        return self._bot


def attach(monkeypatch, bot) -> None:
    monkeypatch.setattr(setup_api, "_qq_adapter", lambda: FakeAdapter(bot))


class TestStatus:
    @pytest.mark.asyncio
    async def test_status_reports_no_adapter_without_crashing(
        self, client, monkeypatch
    ):
        """The page's first request on a backend that has not finished booting.
        A 500 here would leave the student with a blank screen and no way in."""
        monkeypatch.setattr(setup_api, "_qq_adapter", lambda: None)
        body = (await client.get("/campus/setup/status")).json()
        assert body["link"]["adapter_ready"] is False
        assert body["link"]["connected"] is False
        # The self-check still ran: it is about config, not about the socket.
        assert body["checks"]

    @pytest.mark.asyncio
    async def test_a_connected_account_shows_as_linked(self, client, monkeypatch):
        attach(monkeypatch, FakeBot(accounts=["20002"]))
        body = (await client.get("/campus/setup/status")).json()
        assert body["link"]["connected"] is True
        assert body["link"]["accounts"] == ["20002"]

    @pytest.mark.asyncio
    async def test_a_broken_self_check_is_reported_not_raised(
        self, client, monkeypatch
    ):
        """The self-check reads config files and a database; any of them can be
        missing on a fresh clone. The page has to render and say so."""
        from campuscue import provision

        async def boom():
            raise RuntimeError("config unreadable")

        monkeypatch.setattr(provision, "collect_checks", boom)
        monkeypatch.setattr(setup_api, "_qq_adapter", lambda: None)
        body = (await client.get("/campus/setup/status")).json()
        assert body["problems"] == 1
        assert "config unreadable" in body["checks"][0]["text"]

    @pytest.mark.asyncio
    async def test_extractor_needs_both_a_key_and_model(self, client, monkeypatch):
        monkeypatch.setenv("ARK_API_KEY", "present")
        monkeypatch.delenv("ARK_EXTRACT_MODEL", raising=False)
        monkeypatch.delenv("ARK_MODEL", raising=False)
        monkeypatch.setattr(setup_api, "_qq_adapter", lambda: None)

        missing_model = (await client.get("/campus/setup/status")).json()
        monkeypatch.setenv("ARK_MODEL", "ep-test")
        ready = (await client.get("/campus/setup/status")).json()

        assert missing_model["extractor_ready"] is False
        assert ready["extractor_ready"] is True


class TestGroupSync:
    @pytest.mark.asyncio
    async def test_sync_needs_a_connected_account(self, client, monkeypatch):
        attach(monkeypatch, FakeBot(accounts=[]))
        res = await client.post("/campus/setup/groups/sync")
        assert res.status_code == 409

    @pytest.mark.asyncio
    async def test_synced_groups_arrive_unwatched(self, client, monkeypatch):
        """The consent property. Adopting every group an account happens to be in
        would start extracting from unrelated groups on the student's behalf --
        the point of this screen is that watching is chosen."""
        attach(
            monkeypatch,
            FakeBot(
                accounts=["20002"],
                groups=[
                    {"group_id": 998877, "group_name": "软件工程课程群"},
                    {"group_id": 776655, "group_name": "室友群"},
                ],
            ),
        )
        rows = (await client.post("/campus/setup/groups/sync")).json()
        by_umo = {r["umo"]: r for r in rows}
        assert by_umo["qq:GroupMessage:998877"]["label"] == "软件工程课程群"
        assert all(not r["enabled"] for r in rows)

    @pytest.mark.asyncio
    async def test_resync_does_not_mute_a_group_already_watched(
        self, client, monkeypatch
    ):
        """Pressing 同步 again after choosing groups must not undo the choice --
        and silently switching extraction off is the kind of bug nobody notices
        until a deadline is missed."""
        await store.update_source(
            "qq:GroupMessage:998877", display_name="软件工程", enabled=True
        )
        attach(
            monkeypatch,
            FakeBot(
                accounts=["20002"],
                groups=[{"group_id": 998877, "group_name": "软件工程课程群"}],
            ),
        )
        rows = (await client.post("/campus/setup/groups/sync")).json()
        row = next(r for r in rows if r["umo"] == "qq:GroupMessage:998877")
        assert row["enabled"] is True

    @pytest.mark.asyncio
    async def test_resync_preserves_a_name_typed_by_the_student(
        self, client, monkeypatch
    ):
        await store.update_source(
            "qq:GroupMessage:998877", display_name="软件工程", enabled=True
        )
        attach(
            monkeypatch,
            FakeBot(
                accounts=["20002"],
                groups=[{"group_id": 998877, "group_name": "2026软工通知群"}],
            ),
        )

        rows = (await client.post("/campus/setup/groups/sync")).json()

        row = next(r for r in rows if r["umo"] == "qq:GroupMessage:998877")
        assert row["label"] == "软件工程"

    @pytest.mark.asyncio
    async def test_a_failed_group_list_is_a_readable_error(self, client, monkeypatch):
        attach(monkeypatch, FakeBot(accounts=["20002"], fail=True))
        res = await client.post("/campus/setup/groups/sync")
        assert res.status_code == 502
        assert "拉取群列表失败" in res.json()["detail"]

    @pytest.mark.asyncio
    async def test_watch_toggles_extraction_for_one_group(self, client):
        """``CampusSource.enabled`` is what the extractor gates on, so this
        checkbox is the whole of "watch this group"."""
        await store.update_source(UMO, enabled=False)
        umo_path = httpx.URL(f"/campus/setup/groups/{UMO}/watch").path
        row = (await client.post(f"{umo_path}?on=true")).json()
        assert row["enabled"] is True
        source = next(s for s in await store.list_sources() if s.umo == UMO)
        assert source.enabled is True

    @pytest.mark.asyncio
    async def test_a_umo_with_colons_toggles_the_right_group(self, client):
        """``{umo:path}``, not ``{umo}``: the default converter cuts at the first
        colon, and every umo has two."""
        await store.update_source(UMO, enabled=True)
        await store.update_source("qq:GroupMessage:other", enabled=True)
        await client.post(f"/campus/setup/groups/{UMO}/watch?on=false")
        rows = {s.umo: s.enabled for s in await store.list_sources()}
        assert rows[UMO] is False
        assert rows["qq:GroupMessage:other"] is True


class TestSelftest:
    @pytest.mark.asyncio
    async def test_selftest_reports_an_unbound_scheduler(self, client):
        body = (await client.post("/campus/setup/selftest")).json()
        assert body["ok"] is False
        assert "调度器" in body["detail"]

    @pytest.mark.asyncio
    async def test_selftest_pushes_through_the_reminder_path(self, client, monkeypatch):
        """Same ``send_message`` the scheduler uses, so a delivered test means a
        scheduled reminder will land too."""
        sent: list[tuple[str, str]] = []

        class FakeCtx:
            async def send_message(self, umo, chain):
                sent.append((umo, chain.get_plain_text()))
                return True

        monkeypatch.setattr(reminders, "_ctx", FakeCtx())
        monkeypatch.setattr(reminders, "_cron", object())

        body = (await client.post("/campus/setup/selftest")).json()
        assert body["ok"] is True
        assert sent and sent[0][0] == UMO

    @pytest.mark.asyncio
    async def test_a_failed_push_is_reported_not_raised(self, client, monkeypatch):
        class FakeCtx:
            async def send_message(self, umo, chain):
                raise RuntimeError("no platform")

        monkeypatch.setattr(reminders, "_ctx", FakeCtx())
        monkeypatch.setattr(reminders, "_cron", object())
        body = (await client.post("/campus/setup/selftest")).json()
        assert body["ok"] is False
        assert "no platform" in body["detail"]

    @pytest.mark.asyncio
    async def test_a_dead_source_does_not_hide_a_live_one(self, client, monkeypatch):
        """Every watched group is tried, not just the first.

        A board that has been tested keeps sources whose platform is gone (a
        replay session, a retired adapter). ``list_sources`` orders by messages
        seen, so those rank *above* a freshly synced real group -- the demo talked
        and the real group has not yet. Observed for real: the button reported
        没有平台匹配 on a machine where the push would have worked, seconds after
        the student finished connecting QQ.
        """
        # The dead source has traffic behind it, the live one is brand new, which
        # is exactly the order list_sources returns them in.
        await store.update_source(UMO, enabled=True, stat_seen=40)
        await store.update_source("qq:GroupMessage:live", enabled=True)
        assert [s.umo for s in await store.list_sources()][0] == UMO
        sent: list[str] = []

        class FakeCtx:
            async def send_message(self, umo, chain):
                sent.append(umo)
                # Only the real group has a platform behind it.
                return umo == "qq:GroupMessage:live"

        monkeypatch.setattr(reminders, "_ctx", FakeCtx())
        monkeypatch.setattr(reminders, "_cron", object())

        body = (await client.post("/campus/setup/selftest")).json()

        assert body["ok"] is True
        assert "qq:GroupMessage:live" in sent
        assert len(sent) > 1, "应当在第一个来源失败后继续尝试"

    @pytest.mark.asyncio
    async def test_an_explicit_umo_is_not_second_guessed(self, client, monkeypatch):
        """A caller naming a target gets that target, with no fallback sweep."""
        sent: list[str] = []

        class FakeCtx:
            async def send_message(self, umo, chain):
                sent.append(umo)
                return False

        monkeypatch.setattr(reminders, "_ctx", FakeCtx())
        monkeypatch.setattr(reminders, "_cron", object())

        body = (
            await client.post("/campus/setup/selftest?umo=qq:GroupMessage:nope")
        ).json()

        assert body["ok"] is False
        assert sent == ["qq:GroupMessage:nope"]


class TestNapCatEndpoints:
    @pytest.mark.asyncio
    async def test_start_without_an_install_answers_ok_false(self, client, monkeypatch):
        """Not a 500: the panel is the only surface the student has, so a failure
        has to be a sentence in it."""
        monkeypatch.setattr(napcat, "find_home", lambda: (None, None))
        body = (await client.post("/campus/setup/napcat/start")).json()
        assert body["ok"] is False
        assert "还没装" in body["detail"]

    @pytest.mark.asyncio
    async def test_configure_writes_the_current_port(
        self, client, tmp_path, monkeypatch
    ):
        write_config(tmp_path, "ws://127.0.0.1:1111/ws")
        monkeypatch.setattr(napcat, "find_home", lambda: (tmp_path, tmp_path / "l.bat"))
        monkeypatch.setenv("CAMPUSCUE_ONEBOT_PORT", "6199")
        body = (await client.post("/campus/setup/napcat/configure")).json()
        assert body["ok"] is True
        assert napcat.is_configured(tmp_path, "ws://127.0.0.1:6199/ws")

    @pytest.mark.asyncio
    async def test_the_log_endpoint_returns_the_qr_separately(
        self, client, tmp_path, monkeypatch
    ):
        log = tmp_path / "napcat.log"
        log.write_text(QR_BODY, encoding="utf-8")
        monkeypatch.setattr(napcat, "LOG_PATH", log)
        body = (await client.get("/campus/setup/napcat/log")).json()
        assert body["qrcode"].count("\n") == 11
        assert "等待扫码" in body["log"]

    @pytest.mark.asyncio
    async def test_a_missing_log_is_empty_not_an_error(
        self, client, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(napcat, "LOG_PATH", tmp_path / "absent.log")
        # Pinned, because ``running`` now also reports orphaned NapCats -- and the
        # dev machine running these tests may well have one up.
        monkeypatch.setattr(napcat, "foreign_pids", lambda: [])
        body = (await client.get("/campus/setup/napcat/log")).json()
        assert body == {"log": "", "qrcode": "", "running": False}


@pytest.mark.asyncio
async def test_status_lists_groups_with_their_task_counts(client, monkeypatch):
    """The watch list doubles as the only place a student sees which groups have
    produced anything, so the counts have to be real."""
    monkeypatch.setattr(setup_api, "_qq_adapter", lambda: None)
    await store.update_source(UMO, display_name="软件工程课程群", enabled=True)
    task = CampusTask(
        umo=UMO,
        title="实验三报告",
        task_type="homework",
        status="active",
        deadline=datetime.now(timezone.utc) + timedelta(days=2),
        confidence=1.0,
    )
    task.dedup_key = store.dedup_key(task.umo, task.title, task.deadline)
    await store.create_task(task)

    body = (await client.get("/campus/setup/status")).json()
    row = next(s for s in body["sources"] if s["umo"] == UMO)
    assert row["label"] == "软件工程课程群"
    assert row["open_tasks"] == 1
