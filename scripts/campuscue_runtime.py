"""Own and control the local CampusCue runtime process."""

from __future__ import annotations

import _thread
import argparse
import atexit
import json
import os
import runpy
import socket
import threading
import time
import urllib.request
import uuid
import webbrowser
from datetime import UTC, datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = Path(__file__).resolve()
RUNTIME_DIR = ROOT / ".tmp"
STATE_PATH = RUNTIME_DIR / "campuscue-runtime.json"
STOP_PATH = RUNTIME_DIR / "campuscue-stop.json"
DEFAULT_PORT = 6185


def _dashboard_port() -> int:
    """Read the configured dashboard port without exposing other settings."""
    config_path = ROOT / "data" / "cmd_config.json"
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        port = int(config.get("dashboard", {}).get("port", DEFAULT_PORT))
        if 1 <= port <= 65535:
            return port
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return DEFAULT_PORT


def _write_json(path: Path, value: dict[str, object]) -> None:
    """Atomically write a small runtime-control JSON file.

    Args:
        path: Destination path.
        value: JSON-compatible object to persist.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True), encoding="utf-8"
    )
    os.replace(temporary, path)


def _read_state() -> dict[str, object] | None:
    """Return the runtime state when it is structurally valid."""
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    required = {"pid", "create_time", "root", "script", "nonce"}
    return state if isinstance(state, dict) and required <= state.keys() else None


def _owned_process(state: dict[str, object] | None) -> psutil.Process | None:
    """Resolve state only when it still identifies this exact installation."""
    if not state:
        return None
    try:
        if Path(str(state["root"])).resolve() != ROOT:
            return None
        if Path(str(state["script"])).resolve() != SCRIPT:
            return None
        process = psutil.Process(int(state["pid"]))
        if abs(process.create_time() - float(state["create_time"])) > 1:
            return None
        if Path(process.cwd()).resolve() != ROOT:
            return None
        script_arguments = []
        for argument in process.cmdline()[1:]:
            if argument.lower().endswith(".py"):
                candidate = Path(argument)
                if not candidate.is_absolute():
                    candidate = ROOT / candidate
                script_arguments.append(candidate.resolve())
        if SCRIPT not in script_arguments:
            return None
        return process
    except (KeyError, TypeError, ValueError, OSError, psutil.Error):
        return None


def _port_is_free(port: int) -> bool:
    """Return whether the loopback dashboard port can be bound."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def _open_when_ready(port: int) -> None:
    """Open the board after its local HTTP endpoint becomes ready."""
    url = f"http://127.0.0.1:{port}/campus/"
    for _ in range(90):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(1)


def run() -> int:
    """Run CampusCue in the foreground while publishing owned PID state."""
    existing = _owned_process(_read_state())
    if existing:
        print("CampusCue 已经在运行。")
        return 2

    port = _dashboard_port()
    if not _port_is_free(port):
        print(f"端口 {port} 已被其他进程占用。为避免误伤，CampusCue 不会自动停止它。")
        return 2

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    nonce = uuid.uuid4().hex
    state = {
        "pid": os.getpid(),
        "create_time": psutil.Process().create_time(),
        "root": str(ROOT),
        "script": str(SCRIPT),
        "nonce": nonce,
        "started_at": datetime.now(UTC).isoformat(),
        "port": port,
    }
    _write_json(STATE_PATH, state)
    STOP_PATH.unlink(missing_ok=True)

    def clean_runtime_files() -> None:
        current = _read_state()
        if current and current.get("nonce") == nonce:
            STATE_PATH.unlink(missing_ok=True)
        STOP_PATH.unlink(missing_ok=True)

    def watch_for_stop() -> None:
        while True:
            try:
                request = json.loads(STOP_PATH.read_text(encoding="utf-8"))
                if (
                    request.get("nonce") == nonce
                    and int(request.get("pid", -1)) == os.getpid()
                ):
                    _thread.interrupt_main()
                    return
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                pass
            time.sleep(0.25)

    atexit.register(clean_runtime_files)
    threading.Thread(target=watch_for_stop, daemon=True).start()
    threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    os.chdir(ROOT)
    try:
        runpy.run_path(str(ROOT / "main.py"), run_name="__main__")
    except KeyboardInterrupt:
        print("CampusCue 正在停止。")
    finally:
        clean_runtime_files()
    return 0


def stop(timeout: float = 15) -> int:
    """Stop only the process proven to belong to this installation.

    Args:
        timeout: Seconds to allow for application cleanup before forced termination.
    """
    state = _read_state()
    process = _owned_process(state)
    if not process:
        if _port_is_free(_dashboard_port()):
            STATE_PATH.unlink(missing_ok=True)
            print("CampusCue 当前没有运行。")
            return 0
        print("检测到端口占用，但无法证明它属于本目录；已拒绝停止该进程。")
        return 3

    _write_json(
        STOP_PATH,
        {"pid": process.pid, "nonce": state["nonce"], "requested_at": time.time()},
    )
    try:
        process.wait(timeout=timeout)
    except psutil.TimeoutExpired:
        print("正常停止超时，正在结束已验证的 CampusCue 进程。")
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    STATE_PATH.unlink(missing_ok=True)
    STOP_PATH.unlink(missing_ok=True)
    print("CampusCue 已停止。")
    return 0


def status() -> int:
    """Report whether this installation owns a live runtime process."""
    process = _owned_process(_read_state())
    if process:
        print(f"CampusCue 正在运行，PID {process.pid}。")
        return 0
    if _port_is_free(_dashboard_port()):
        print("CampusCue 当前没有运行。")
        return 1
    print("CampusCue 未运行，但看板端口被其他进程占用。")
    return 3


def main() -> int:
    """Dispatch the runtime command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "stop", "status"))
    parser.add_argument("--timeout", type=float, default=15)
    arguments = parser.parse_args()
    if arguments.action == "run":
        return run()
    if arguments.action == "stop":
        return stop(arguments.timeout)
    return status()


if __name__ == "__main__":
    raise SystemExit(main())
