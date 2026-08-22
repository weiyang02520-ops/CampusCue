# M7.3 Bounded Agent Copilot Evidence

Status: final evidence; External Final Review PASS.

## What is proven

- All Agent writes (`task_create`, `task_update`, `task_complete`,
  `task_dismiss`) are classified by `ToolDefinition` metadata and blocked
  until an exact confirmation phrase is received.
- Pending arguments are frozen in memory and bound to the current Agent
  thread and source. Rejection, ambiguous confirmation, replay, cross-source
  confirmation, and runtime restart are covered by focused tests.
- Grounding uses the existing source-scoped read tool before update/complete/
  dismiss proposals. Deadline phrases still use the deterministic normalizer.
- `tool_activity` is returned through the existing `/api/v1/agent/chat` field
  and is rendered as safe high-level labels. It contains no raw arguments,
  source IDs, source text, provider request, or trace ID.
- The scheduled reminder copy is truthful in default `delivery=noop` mode:
  “提醒已计划，等待触发。”

## SOURCE-BOUND THREAD FINAL FIX

The external review found one blocker in cross-source conversation reuse. The
backend now binds an in-memory Agent thread to its first source and fails closed
before reading old history, beginning a new turn, or invoking the provider when
an existing thread is presented under another source. Pending cross-source
confirmation remains cancelled with zero mutation. `thread_summary` keeps the
original source binding. The WebUI also clears `conversation` and `messages`
when the selected source changes, so the next request starts a fresh context.

- Same-source continuity = PASS.
- Cross-source conversation history leakage = 0.
- Cross-source pending mutation = 0.
- WebUI source switch reset = PASS.

## M7-A10 local deterministic loop

Command:

```powershell
cd v2
$env:PYTHONPATH = "src"
.\.venv-demo\Scripts\python.exe -m pytest tests/integration/test_m73_full_demo.py -q
```

The harness uses a temporary SQLite database, the official M7 fixture, real
`TaskPipeline`, `TaskService`, `ReminderService`, `CampusAgentRuntime`, and
deterministic provider/sink doubles. It records Step 0–16, a real wall-clock
duration, and writes `a10-local.json` in this directory. It does not run real
QQ or use real secrets.

## Visual evidence

- `m73-agent-read-1440.png`
- `m73-agent-confirm-1440.png`
- `m73-agent-confirmed-1440.png`
- `m73-five-minute-home-1440.png`
- `m73-agent-confirm-390.png`
- `m73-final-home-390.png`

Captured by `v2/web/tests/e2e/m73-agent-copilot.spec.ts` with mocked API data;
the screenshots prove the confirmation/activity presentation, not a real
provider or QQ delivery.

## Explicit limits

- M7.2 Fake NapCat reminder E2E = PASS; Real QQ M7 E2E = NOT_RUN.
- Real QQ M7 E2E = NOT_RUN is an accepted limitation, not a Final Gate blocker.
- No durable approval memory, approval table, new API endpoint, schema
  migration, additional channel, automatic retry, or M7.4.
