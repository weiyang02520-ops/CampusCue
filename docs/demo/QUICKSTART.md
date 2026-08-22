# CampusCue V2 Quick Start

This is the local, loopback-first path for the M7 demo. It uses Python 3.12+
or newer, Node.js/npm for the WebUI, and no real QQ credentials are required
for the deterministic acceptance harness.

## Install

```powershell
cd v2
py -3.12 -m venv .venv-demo
.\.venv-demo\Scripts\python.exe -m pip install -e ".[test]"
cd web
npm install
```

Confirm the Python import points to `v2/src`, not the legacy root package:

```powershell
cd ..
.\.venv-demo\Scripts\python.exe -c "import campuscue; print(campuscue.__file__)"
```

## Configure

Copy `v2/.env.example` to a local environment file or set the variables in
PowerShell. Keep `CAMPUSCUE_API_HOST=127.0.0.1`, use a local random API token,
and leave `CAMPUSCUE_REMINDER_DELIVERY=noop` unless an isolated OneBot test
group has been explicitly selected.

The Agent needs an enabled Provider configured through the existing Provider
settings/API. Provider keys remain environment-only and are never committed.

## Start

In one PowerShell window:

```powershell
cd v2
.\.venv-demo\Scripts\python.exe -m campuscue
```

In a second window:

```powershell
cd v2/web
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`. The backend
API is normally `http://127.0.0.1:6200`; the WebUI proxy uses the configured
local API token.

## Deterministic acceptance

No database rows need to be deleted manually:

```powershell
cd v2
$env:PYTHONPATH = "src"
.\.venv-demo\Scripts\python.exe -m pytest tests/integration/test_m73_full_demo.py -q
```

This creates an isolated temporary SQLite database and writes local evidence
to `.ai-handoff/evidence/m73/a10-local.json`. It uses the official fixture,
real TaskPipeline/TaskService/ReminderService/AgentRuntime, and deterministic
provider/sink doubles. It does not run a real QQ test.
