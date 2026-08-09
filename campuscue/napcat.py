"""Manage a local NapCat so the QQ link can be set up from the board.

Why this is in the product rather than in a README
--------------------------------------------------
Connecting a real QQ account is the one step nobody can do for the student: a
scan on a phone. Everything *around* that step, though, is exactly the kind of
work that goes wrong while someone is watching -- download the right release,
put the reverse-WebSocket address in the right config file under the right
name, start the launcher, find the QR, notice that the socket came up. Each of
those has a single correct answer that this module already knows, so the board
can do them and leave the student with one job.

What NapCat is, in the two facts that matter here:

* It is a OneBot v11 implementation driving a locally installed QQNT. astrbot's
  ``AiocqhttpAdapter`` listens on :6199 and NapCat dials in, so the address only
  ever has to be configured on NapCat's side -- which is why the config written
  below is the whole of the wiring.
* Its per-account config is ``config/onebot11_<uin>.json``, created from
  ``config/onebot11.json`` the first time an account logs in. The uin is not
  known until after the scan, so the template is what has to be right; the
  per-account file is reconciled afterwards by ``apply_config``.

Deliberately not modelled here: login state. NapCat's own webui would have to be
polled for it, and there is a better signal already in the process -- when the
adapter's reverse-WS gains a client, that account is logged in and its uin is in
the handshake. ``campuscue/api/setup.py`` reads it from there, so this module
never has to guess.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field

import httpx

from astrbot.core import logger

DATA_DIR = pathlib.Path("data").resolve()
HOME = DATA_DIR / "napcat"
"""Where a board-installed NapCat lives. Under ``data/`` so it shares the
directory the rest of the deployment's mutable state is already in, and so a
student who wants to start over can delete one folder."""

LOG_PATH = DATA_DIR / "napcat.log"
"""Console output, appended across restarts.

Kept as a file rather than an in-memory ring buffer because it is the only place
the login QR appears in a form this process can show: NapCat draws the QR as
block characters on stdout, and rendering that log verbatim in a monospace panel
is a scannable QR code with no image handling at all."""

RELEASE_URL = (
    "https://github.com/NapNeko/NapCatQQ/releases/latest/download/NapCat.Shell.zip"
)
"""The Shell build: drives an already-installed QQNT rather than bundling one.

Pinned to ``latest`` rather than a version because NapCat tracks QQ's own
updates -- a pinned release stops working when QQ updates itself, which on a
student laptop happens without asking."""

DOWNLOAD_TIMEOUT = 600.0

_proc: subprocess.Popen | None = None
"""The NapCat we started. Only ever this one: a NapCat the student launched
themselves is theirs to stop, and killing by image name would take QQ with it."""


class NapCatError(RuntimeError):
    """Something the student can act on, phrased for the panel."""


@dataclass
class State:
    """Everything the panel needs to decide which button to offer."""

    installed: bool = False
    home: str = ""
    launcher: str = ""
    running: bool = False
    pid: int | None = None
    managed: bool = False
    """True when the running process is one we started, so we may stop it."""
    configured: bool = False
    """The reverse-WS address in NapCat's config matches the port we listen on."""
    ws_url: str = ""
    installing: bool = False
    supported: bool = True
    detail: str = ""
    accounts: list[str] = field(default_factory=list)
    """Uins with a per-account config, i.e. accounts that have logged in here."""


_installing = False


def ws_url() -> str:
    """The address NapCat must dial.

    ``127.0.0.1`` rather than the adapter's bind address: one is
    where we listen, the other is where a client connects, and writing the bind
    address into a client config is a connection that never opens.
    """
    port = os.environ.get("CAMPUSCUE_ONEBOT_PORT", "6199")
    return f"ws://127.0.0.1:{port}/ws"


def _candidates() -> list[pathlib.Path]:
    """Where a NapCat might already be, most specific first."""
    found = [HOME]
    override = os.environ.get("CAMPUSCUE_NAPCAT_DIR", "").strip()
    if override:
        found.insert(0, pathlib.Path(override).expanduser())
    for base in (pathlib.Path("C:/"), pathlib.Path.home(), DATA_DIR.parent):
        for name in ("NapCat", "NapCatQQ", "NapCat.Shell", "napcat"):
            found.append(base / name)
    return found


def _launcher_in(home: pathlib.Path) -> pathlib.Path | None:
    """The launcher script, if this directory is a NapCat Shell install.

    Four launchers ship side by side, and the ``-user`` ones are the only ones
    this process can drive. The plain ``launcher.bat`` and ``launcher-win10.bat``
    open with ``net session`` to test for administrator rights, and when they do
    not have them they relaunch themselves through UAC
    (``Start-Process -Verb runAs``) and immediately ``exit``. That breaks the two
    things the panel is built on: the pid we started is gone a moment later, so
    ``running`` goes false while QQ is in fact starting, and the elevated child
    writes its console to a new window instead of our redirected log -- so the
    login QR never reaches the page and the wait never ends.

    The ``-user`` scripts do the same work (same env vars, same registry lookup
    for QQ.exe, same boot hook) with no elevation check, so they are preferred
    and the admin ones are last-resort fallbacks for an install that omits them.
    """
    if not home.is_dir():
        return None
    for name in (
        "launcher-user.bat",
        "launcher-win10-user.bat",
        "launcher.bat",
        "launcher-win10.bat",
    ):
        candidate = home / name
        if candidate.is_file():
            return candidate
    return None


def find_home() -> tuple[pathlib.Path | None, pathlib.Path | None]:
    """Locate an install. Returns ``(home, launcher)``, either may be None."""
    for candidate in _candidates():
        launcher = _launcher_in(candidate)
        if launcher is not None:
            return candidate, launcher
    return None, None


# --- config --------------------------------------------------------------


def onebot_config(url: str) -> dict:
    """NapCat's OneBot v11 config, holding one reverse-WS target.

    Shape is NapCat's, and the two fields worth explaining:

    * ``reverseWs.enable`` is what makes NapCat dial out at all; with it false
      the socket never opens and nothing in astrbot's logs says why.
    * ``messagePostFormat: "array"`` keeps message segments as a list, which is
      what ``convert_message`` iterates. The alternative, ``"string"``, collapses
      images and @-mentions into CQ codes that the adapter would have to reparse.

    ``debug`` stays off: it echoes every message body into NapCat's log, and that
    log is rendered in a browser panel on this machine.
    """
    return {
        "network": {
            "httpServers": [],
            "httpClients": [],
            "websocketServers": [],
            "websocketClients": [
                {
                    "name": "campuscue",
                    "enable": True,
                    "url": url,
                    "reportSelfMessage": False,
                    "messagePostFormat": "array",
                    "token": os.environ.get("CAMPUSCUE_ONEBOT_TOKEN", ""),
                    "debug": False,
                    "heartInterval": 30000,
                    "reconnectInterval": 5000,
                }
            ],
        },
        "musicSignUrl": "",
        "enableLocalFile2Url": False,
        "parseMultMsg": True,
    }


def _config_files(home: pathlib.Path) -> list[pathlib.Path]:
    """The template plus every per-account config already created.

    Both have to be written. The template is what a *new* account inherits, and
    the per-account files are what accounts that already logged in here actually
    read -- fixing only the template is the failure where re-scanning with the
    same QQ silently keeps the old address.
    """
    config_dir = home / "config"
    if not config_dir.is_dir():
        return [config_dir / "onebot11.json"]
    files = [config_dir / "onebot11.json"]
    files += sorted(config_dir.glob("onebot11_*.json"))
    return files


def known_accounts(home: pathlib.Path) -> list[str]:
    """Uins that have a per-account config, i.e. have logged in on this install."""
    config_dir = home / "config"
    if not config_dir.is_dir():
        return []
    return sorted(
        path.stem.removeprefix("onebot11_")
        for path in config_dir.glob("onebot11_*.json")
    )


def is_configured(home: pathlib.Path, url: str) -> bool:
    """True when every config present already points at ``url``.

    Every, not any: an install with a stale per-account file connects with the
    stale address for that account, so a partial match is not configured.
    """
    files = [path for path in _config_files(home) if path.is_file()]
    if not files:
        return False
    for path in files:
        try:
            body = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        clients = (body.get("network") or {}).get("websocketClients") or []
        if not any(c.get("enable") and c.get("url") == url for c in clients):
            return False
    return True


def apply_config(home: pathlib.Path, url: str) -> list[str]:
    """Point the template and every per-account config at ``url``.

    Rewrites the whole file rather than patching the client list. A student who
    has been trying to get this working by hand may have left several disabled or
    half-correct clients behind, and merging into that is how you end up with
    NapCat dialling two addresses. One known-good client is the intent.
    """
    written: list[str] = []
    config_dir = home / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    body = json.dumps(onebot_config(url), ensure_ascii=False, indent=2)
    for path in _config_files(home):
        if path.is_file() and path.read_text(encoding="utf-8").strip() == body:
            continue
        # Atomic write: a crash mid-write must not leave NapCat with a truncated
        # config, which it would silently re-initialise into an unconfigured one.
        fd, tmp_path = tempfile.mkstemp(
            prefix=path.stem, suffix=".tmp", dir=str(config_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(body)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        written.append(path.name)
    return written


# --- install -------------------------------------------------------------


async def install() -> pathlib.Path:
    """Download and unpack NapCat Shell into ``data/napcat``.

    Serialised by a module flag: the panel's button is disabled while this runs,
    but a second browser tab is not, and two concurrent unpacks into one
    directory produce a half-written install that then fails to launch for a
    reason nobody can read.

    The zip is streamed to a temp file rather than held in memory (it is ~30 MB)
    and unpacked to a staging directory that only replaces the real one on
    success, so a download that dies halfway leaves the previous install intact.
    """
    global _installing
    if _installing:
        raise NapCatError("正在安装，稍等")
    if sys.platform != "win32":
        raise NapCatError("自动安装只支持 Windows，其他系统请手动装 NapCat")

    _installing = True
    try:
        HOME.parent.mkdir(parents=True, exist_ok=True)
        archive = HOME.parent / "napcat-download.zip"
        staging = HOME.parent / "napcat-staging"

        logger.info("[campuscue] 下载 NapCat: %s", RELEASE_URL)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream(
                "GET", RELEASE_URL, timeout=DOWNLOAD_TIMEOUT
            ) as response:
                response.raise_for_status()
                with archive.open("wb") as handle:
                    async for chunk in response.aiter_bytes(1 << 16):
                        handle.write(chunk)

        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        # Blocking work off the event loop: unpacking the archive stalls the SSE
        # heartbeat and the board would show 连接中断 mid-install.
        await asyncio.to_thread(_unpack, archive, staging)

        root = _shell_root(staging)
        if root is None:
            raise NapCatError("压缩包里找不到 launcher，可能下载到了错误的版本")

        if HOME.exists():
            shutil.rmtree(HOME, ignore_errors=True)
        await asyncio.to_thread(_publish, root, HOME)
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)

        apply_config(HOME, ws_url())
        logger.info("[campuscue] NapCat 已安装到 %s", HOME)
        return HOME
    except httpx.HTTPError as exc:
        raise NapCatError(f"下载失败：{exc}") from exc
    finally:
        _installing = False


def _unpack(archive: pathlib.Path, target: pathlib.Path) -> None:
    """Extract an archive, refusing any member that escapes ``target``.

    The download is over HTTPS from a pinned GitHub release, so this is defence
    in depth rather than a response to an observed attack -- but a malicious or
    corrupted archive whose members are ``../`` paths would otherwise write
    straight into ``data/`` next to the database and config.
    """
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise NapCatError(
                    f"压缩包内包含越界路径：{member.filename!r}，已中止解压"
                )
        zf.extractall(target)


PUBLISH_ATTEMPTS = 8
PUBLISH_WAIT = 1.0


def _publish(root: pathlib.Path, home: pathlib.Path) -> None:
    """Move the unpacked install into place, retrying a locked directory.

    Observed on a clean Windows 11 machine: the rename immediately after
    extraction fails with ``WinError 5``, then succeeds a second later. The
    archive contains ``.exe`` and ``.dll`` files, and Defender's real-time scan
    opens each one as it is written -- so the directory is still busy at the
    moment the extraction call returns. Nothing in the process is holding it, so
    there is nothing to close; the only fix is to wait it out.

    Retried rather than reported because the student cannot act on it, and
    "拒绝访问" on a fresh install reads as a permissions problem they are
    supposed to go fix. Eight tries is generous for a scan of ~30MB; if it is
    still locked after that, something really is holding the directory and the
    error should surface.
    """
    for attempt in range(PUBLISH_ATTEMPTS):
        try:
            root.rename(home)
            return
        except OSError as exc:
            if attempt == PUBLISH_ATTEMPTS - 1:
                raise NapCatError(
                    f"装好了但移动不过去，可能是杀毒软件正在扫描，稍等再点一次：{exc}"
                ) from exc
            time.sleep(PUBLISH_WAIT)


def _shell_root(staging: pathlib.Path) -> pathlib.Path | None:
    """Find the directory holding the launcher.

    Releases have shipped both flat and inside a single top-level folder, so the
    layout is discovered rather than assumed.
    """
    if _launcher_in(staging) is not None:
        return staging
    for child in sorted(staging.iterdir()):
        if _launcher_in(child) is not None:
            return child
    return None


# --- process -------------------------------------------------------------


BOOT_EXE = "napcatwinbootmain.exe"
"""NapCat Shell's entry process on Windows. It is what the launcher .bat starts,
and unlike the .bat it stays alive for the whole session, so it is the process to
look for when deciding whether a NapCat is already up."""


def foreign_pids() -> list[int]:
    """Pids of NapCats running out of our install directory that we did not start.

    Why this has to exist: ``_proc`` is module state, so restarting the backend
    forgets the NapCat it launched while that NapCat keeps running. The next
    ``start()`` then sees "not running", launches a second one against the same
    QQ install, and both append to ``data/napcat.log`` -- which is where the QR is
    read from. Two interleaved streams of expiring codes is a page that can never
    show a current one.

    Scoped to processes whose executable lives under our HOME, so a NapCat the
    student installed elsewhere and runs themselves is left out of this entirely.
    """
    ours = _proc.pid if _proc is not None else None
    home = str(HOME).lower()
    found: list[tuple[float, int]] = []
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a hard dependency
        return []
    for proc in psutil.process_iter(["pid", "name", "create_time"]):
        try:
            if (proc.info["name"] or "").lower() != BOOT_EXE:
                continue
            if not (proc.exe() or "").lower().startswith(home):
                continue
            if proc.pid == ours or proc.ppid() == ours:
                continue
            found.append((proc.info["create_time"] or 0.0, proc.pid))
        except (psutil.Error, OSError):
            continue
    return [pid for _, pid in sorted(found, reverse=True)]


def is_running() -> bool:
    """Whether any NapCat from our install is up, ours or an orphan."""
    if _proc is not None and _proc.poll() is None:
        return True
    return bool(foreign_pids())


def start() -> int:
    """Launch NapCat with its console redirected to ``data/napcat.log``.

    That redirect is the whole trick behind the QR on the web page: NapCat draws
    the login code with block characters on stdout, so a log tail rendered in a
    monospace panel *is* the QR — no image decoding, no screenshot, nothing to
    get wrong.
    """
    global _proc
    if _proc is not None and _proc.poll() is None:
        return _proc.pid

    home, launcher = find_home()
    if home is None or launcher is None:
        raise NapCatError("还没装 NapCat，先点安装")

    # Clear orphans before launching, or the page can never show a live QR.
    # An orphan holds the log fd it inherited from the backend that started it and
    # keeps writing at its own offset, so truncating the log below does not stop
    # it: the file ends up interleaving two NapCats' QR reprints, and every code
    # the panel picks is one the other process has already superseded.
    #
    # Safe to end without asking, on two counts: it runs out of our own install
    # directory, so it is ours and not a NapCat the student manages themselves;
    # and it is unreachable anyway, since the backend it reported to is gone.
    for pid in foreign_pids():
        logger.warning("[campuscue] 清理上次残留的 NapCat pid=%s", pid)
        _kill_tree(pid)

    apply_config(home, ws_url())

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Truncate: the log is read as "what happened during this login", and a stale
    # QR from the last run scrolling above the live one is worse than no history.
    log = LOG_PATH.open("w", encoding="utf-8", errors="replace")
    try:
        kwargs: dict = {
            "cwd": str(home),
            "stdout": log,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # Own process group, no console window: a stray Ctrl-C in the
            # terminal running the board must not take the QQ session down.
            kwargs["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
            )
            # Absolute path, not the bare name: a machine with
            # NoDefaultCurrentDirectoryInExePath=1 set (this one) makes cmd
            # refuse to resolve a script from the working directory, and the
            # only trace is "不是内部或外部命令" in the log where the QR
            # should be.
            args = ["cmd", "/c", str(launcher)]
        else:
            args = [str(launcher)]
        _proc = subprocess.Popen(args, **kwargs)
    except OSError as exc:
        log.close()
        raise NapCatError(f"启动失败：{exc}") from exc

    logger.info("[campuscue] NapCat 已启动 pid=%s", _proc.pid)
    return _proc.pid


def _kill_tree(pid: int) -> None:
    """End a process and its children.

    Whole tree, because the launcher .bat spawns NapCat which spawns QQ.exe;
    killing only the parent orphans the rest, and an orphan still holds the
    reverse-WS connection and the log fd.
    """
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)],
            capture_output=True,
            check=False,
        )
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass


def stop() -> bool:
    """Stop the NapCat we started, plus any orphan from a previous backend run.

    Orphans are included because they are indistinguishable from ours to the
    student: the page says 运行中 either way, and 停止 that leaves one alive is a
    button that visibly does nothing.
    """
    global _proc
    stopped = False
    proc = _proc
    if proc is not None and proc.poll() is None:
        _kill_tree(proc.pid)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logger.info("[campuscue] NapCat 已停止 pid=%s", proc.pid)
        stopped = True
    _proc = None
    for pid in foreign_pids():
        logger.info("[campuscue] 清理残留 NapCat pid=%s", pid)
        _kill_tree(pid)
        stopped = True
    return stopped


def tail(lines: int = 200) -> str:
    """Last ``lines`` of the NapCat console, for the QR panel.

    Read as bytes then decoded loosely: NapCat writes GBK-ish Windows console
    output alongside the QR's box-drawing characters, and one undecodable byte
    must not blank the panel the student is trying to scan.
    """
    if not LOG_PATH.exists():
        return ""
    raw = LOG_PATH.read_bytes()
    if len(raw) > 256_000:
        raw = raw[-256_000:]
    text = raw.decode("utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])


def qrcode_block(text: str | None = None) -> str:
    """Pull just the QR out of the log.

    The panel could render the whole tail, but the QR needs a tight monospace
    box and the surrounding log lines are long enough to force wrapping, which
    breaks the code. Detected structurally — a run of lines made only of block
    characters and spaces — because NapCat's surrounding wording changes between
    versions while the drawing characters do not.

    Each line is normalised first, and both normalisations fix a case where the
    QR is sitting in the log and the panel would show nothing:

    * The usual Python QR renderers draw white modules as U+00A0, not a space
      (a plain space at the end of a line gets stripped by terminals and breaks
      the grid), so a strict space-only test rejects every real code.
    * A console redirected to a file keeps its ANSI colour codes, which put
      ``ESC[...m`` in the middle of otherwise pure block-character lines.
    """
    body = tail(400) if text is None else text
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in body.splitlines():
        stripped = _ANSI_RE.sub("", line).translate(_SPACES).rstrip()
        if stripped and not (set(stripped) - _QR_CHARS):
            current.append(stripped)
            continue
        if len(current) >= QR_MIN_LINES:
            blocks.append(current)
        current = []
    if len(current) >= QR_MIN_LINES:
        blocks.append(current)
    # The last block, not the longest one. NapCat reprints the QR every two
    # minutes as the previous code expires, and each reprint is the same height
    # as the last -- so a longest-wins scan returns the *first* one every time and
    # the panel shows a code that expired minutes ago. Observed for real: seven
    # codes in the log, all 18 lines, and every scan reported 二维码过期.
    return "\n".join(blocks[-1]) if blocks else ""


QR_MIN_LINES = 8
"""Shortest run of block-character lines that counts as a QR.

A real code is ~18 lines with half-block rendering. Anything shorter is a box
border or a progress bar, and admitting those would make "the last block" pick
one of them over the code above it.
"""

_QR_CHARS = set(" \t█▀▄▐▌░▒▓■□◼◻")

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

_SPACES = {
    # Space-like characters a QR renderer uses for a white module -- the
    # common one is U+00A0, chosen precisely because a trailing plain space
    # gets stripped and breaks the grid. All of these are narrow, so mapping
    # them to a plain space preserves module width; the double-width
    # ideographic space is deliberately absent, since collapsing it to one
    # space would halve that module.
    ord(char): " "
    for char in "               "
}


def status() -> State:
    """Everything the 接入 panel needs about NapCat in one read."""
    home, launcher = find_home()
    url = ws_url()
    mine = _proc is not None and _proc.poll() is None
    orphans = [] if mine else foreign_pids()
    state = State(
        installed=home is not None and launcher is not None,
        home=str(home) if home else "",
        launcher=str(launcher) if launcher else "",
        running=mine or bool(orphans),
        pid=_proc.pid if mine and _proc else (orphans[0] if orphans else None),
        managed=mine,
        ws_url=url,
        installing=_installing,
        supported=sys.platform == "win32",
    )
    if home is not None:
        state.configured = is_configured(home, url)
        state.accounts = known_accounts(home)
    if not state.supported:
        state.detail = "非 Windows 环境，NapCat 需要手动安装启动"
    elif not state.installed:
        state.detail = "未安装"
    elif orphans:
        # Said out loud, because this is the state where a stale QR comes from and
        # the fix ("重新出码" restarts it) is not obvious from 运行中 alone.
        state.detail = f"运行中（上次遗留的进程 pid {orphans[0]}，重新出码会先清掉它）"
    elif state.running:
        state.detail = "运行中"
    else:
        state.detail = "已安装，未启动"
    return state
