from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCRIPT = ROOT / "scripts" / "campuscue_runtime.py"


def test_runtime_can_stop_only_its_owned_process(tmp_path: Path) -> None:
    install_root = tmp_path / "CampusCue"
    scripts = install_root / "scripts"
    data = install_root / "data"
    scripts.mkdir(parents=True)
    data.mkdir()
    shutil.copy2(RUNTIME_SCRIPT, scripts / RUNTIME_SCRIPT.name)
    (install_root / "main.py").write_text(
        "import time\nwhile True:\n    time.sleep(0.1)\n", encoding="utf-8"
    )

    port_probe = socket.socket()
    port_probe.bind(("127.0.0.1", 0))
    port = port_probe.getsockname()[1]
    port_probe.close()
    (data / "cmd_config.json").write_text(
        json.dumps({"dashboard": {"port": port}}), encoding="utf-8"
    )

    process = subprocess.Popen(
        [sys.executable, str(scripts / RUNTIME_SCRIPT.name), "run"],
        cwd=install_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    state_path = install_root / ".tmp" / "campuscue-runtime.json"
    try:
        for _ in range(100):
            if state_path.exists():
                break
            if process.poll() is not None:
                pytest.fail(f"runtime exited early: {process.stdout.read()}")
            time.sleep(0.05)
        else:
            pytest.fail("runtime did not publish its PID state")

        result = subprocess.run(
            [
                sys.executable,
                str(scripts / RUNTIME_SCRIPT.name),
                "stop",
                "--timeout",
                "3",
            ],
            cwd=install_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert process.wait(timeout=5) == 0
        assert not state_path.exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_runtime_refuses_to_stop_an_unowned_port(tmp_path: Path) -> None:
    install_root = tmp_path / "CampusCue"
    scripts = install_root / "scripts"
    data = install_root / "data"
    scripts.mkdir(parents=True)
    data.mkdir()
    shutil.copy2(RUNTIME_SCRIPT, scripts / RUNTIME_SCRIPT.name)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    (data / "cmd_config.json").write_text(
        json.dumps({"dashboard": {"port": port}}), encoding="utf-8"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(scripts / RUNTIME_SCRIPT.name), "stop"],
            cwd=install_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )
        assert result.returncode == 3
        assert listener.getsockname()[1] == port
    finally:
        listener.close()
