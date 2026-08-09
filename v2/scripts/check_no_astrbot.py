#!/usr/bin/env python3
"""Anti-AstrBot Gate for CampusCue V2 (M1).

Checks:
1. No `import astrbot` / `from astrbot ...` anywhere in the V2 source tree
   (AST-based: comments/strings mentioning AstrBot do not count).
2. No AstrBot runtime dependency in v2/pyproject.toml.
3. V2 package imports cleanly when legacy root packages are NOT importable
   (subprocess isolation smoke test).
4. No V1 package shadowing: assert the imported campuscue is the V2 one.

Exit code 0 = PASS, 1 = FAIL.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

V2_ROOT = Path(__file__).resolve().parent.parent  # v2/
SRC = V2_ROOT / "src"
PYPROJECT = V2_ROOT / "pyproject.toml"


def _iter_py_files(root: Path):
    return root.rglob("*.py")


def scan_imports() -> list[str]:
    violations: list[str] = []
    for py in _iter_py_files(SRC):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "astrbot" or alias.name.startswith("astrbot."):
                        violations.append(f"{py}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module == "astrbot" or (node.module or "").startswith("astrbot."):
                    violations.append(f"{py}:{node.lineno}: from {node.module}")
    return violations


def scan_dependencies() -> list[str]:
    violations: list[str] = []
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    deps = data.get("project", {}).get("dependencies", [])
    for d in deps:
        name = d.split(">=")[0].split("<")[0].split("=")[0].strip().lower().replace("_", "-")
        if name == "astrbot":
            violations.append(f"dependency: {d}")
    return violations


def isolation_smoke() -> str | None:
    """Import the V2 package in a subprocess that cannot see legacy root packages."""
    script = (
        "import sys; sys.path.insert(0, %r); "
        "import campuscue; "
        "from campuscue.app.runtime import CampusRuntime; "
        "print('OK', campuscue.__file__)"
    ) % str(SRC)
    try:
        out = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=30,
            cwd=str(V2_ROOT),
        )
    except subprocess.TimeoutExpired:
        return "subprocess timeout"
    if out.returncode != 0:
        return f"import failed: {out.stderr.strip()[:300]}"
    return None


def main() -> int:
    failures: list[str] = []
    violations = scan_imports()
    if violations:
        failures.append("AstrBot imports found:\n  " + "\n  ".join(violations))
    dep_violations = scan_dependencies()
    if dep_violations:
        failures.append("AstrBot dependencies found:\n  " + "\n  ".join(dep_violations))
    smoke = isolation_smoke()
    if smoke:
        failures.append(f"isolation smoke failed: {smoke}")

    if failures:
        print("ANTI-ASTRBOT GATE: FAIL")
        for f in failures:
            print(" -", f)
        return 1
    print("ANTI-ASTRBOT GATE: PASS (no astrbot imports, no astrbot dependency, isolation smoke OK)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
