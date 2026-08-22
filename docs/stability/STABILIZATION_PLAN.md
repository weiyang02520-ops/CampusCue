# CampusCue Post-M7 Stabilization Plan

> Phase: POST-M7 P0 REAL-WORLD RELIABILITY AUDIT
> Current gate: `COMPLETE_AWAITING_EXTERNAL_REVIEW`
> Baseline: `143e85fb2511071d3fcf1e4d6040a3546cd70c2b`
> This is a test and evidence plan. It is not an implementation authorization.

## 1. Current decision

- `M7 FINAL = PASS` remains unchanged.
- `DAILY-USE CANDIDATE = NOT_READY`.
- `M8 = NOT_AUTHORIZED`.
- No product feature expansion, UI iteration, schema migration, API redesign, new connector, automatic retry, durable Agent memory, or second delivery channel is included.

The purpose of stabilization is to prove the existing product boundary under real failure, not to make the boundary larger.

## 1A. P1A checkpoint (2026-08-22)

- `POST-M7 P0 RELIABILITY AUDIT = PASS`.
- `POST-M7 P1A SAFETY & DATA INTEGRITY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`.
- The authorized disposable/fake Track A subset is complete: SQLite lock/commit, Task→Reminder recovery, restore, OneBot connection generation, controlled stop/reopen, Agent concurrency, and browser stale-response coverage.
- One restore ordering defect was reproduced and fixed with explicit parent/child flushes; no schema/API/protocol redesign was made.
- `DAILY-USE CANDIDATE = NOT_READY`; `REAL QQ / REAL PROVIDER = NOT_AUTHORIZED`; `M8 = NOT_AUTHORIZED`.
- Evidence: `.ai-handoff/evidence/stability/p1a/README.md` and `results.json`.

## 2. Evidence order

### Track A — P0 safety and data integrity

Run first, on disposable databases and isolated accounts only:

1. SQLite lock, busy timeout, and injected commit failure during extraction/task/reminder writes.
2. Task commit → reminder planning crash gaps at each awaitable boundary; restart and run `resync_all()`.
3. Corrupt/incompatible logical backup restore, including FK, duplicate-key, missing-field, and flush/commit failures.
4. Agent source mismatch and mutation confirmation under browser retries and concurrent requests.
5. NapCat disconnect/replacement during an outbound action and during a reminder fire.

Pass means canonical facts are either unchanged or changed exactly once, failures are safe and classified, no secret/PII appears in logs or responses, and no unapproved outbound action is emitted.

### Track B — Real integrations

Only after Track A passes:

1. One isolated Real QQ/NapCat source and disposable group.
2. One safe Real Provider smoke using a disposable configuration and non-sensitive prompt.
3. One complete source → extraction → task → reminder → Agent read path with captured evidence.

The real environment must verify target identity, provider error UX, source provenance, reminder state, and cleanup. It must not use production group IDs, private chat content, or long-lived secrets in committed evidence.

### Track C — Lifecycle and recovery

Exercise:

- graceful SIGTERM while API, WS action, bus handler, scheduler callback, and DB write are active;
- startup with occupied API port and partial component failure;
- clean stop/start with the same DB;
- reconnect after API/OneBot interruption;
- missed reminder behavior after downtime.

Pass means no orphaned owned task, no duplicate canonical mutation, no duplicate reminder send within the supported single-runtime boundary, and a truthful health/status result after recovery.

### Track D — Soak and observation

Minimum design:

- 30-minute controlled soak before daily-use candidacy;
- 6-hour candidate soak with synthetic messages, task reads, Agent reads, SSE reconnects, reminder state transitions, and one planned WS reconnect;
- collect snapshots every 60 seconds: process RSS, SQLite size, EventBus queue/in-flight counts, OneBot connection/pending actions, SSE subscribers, Agent threads/pending approvals, reminder jobs, and error counts.

No “no visible problem” result is sufficient without start/end counts and a log scan.

## 3. Test isolation rules

- Use a fresh temporary SQLite database for every fault-injection case.
- Use Fake NapCat for deterministic protocol tests; use a disposable Real QQ group only for the explicitly approved real smoke.
- Use MockTransport or a controllable local proxy for provider failures; do not send real private data.
- Never restore over the project database. Keep the pre-test logical backup and the disposable DB path outside committed artifacts.
- Redact access tokens, provider secrets, QQ IDs, group IDs, private message text, and local private paths from evidence.
- Do not rerun the full 513-test V2 suite, full 41-test Chromium suite, Real Provider, or Real QQ as part of this audit unless a follow-up gate explicitly authorizes the exact run.

## 4. Exit criteria for DAILY-USE CANDIDATE

The candidate remains `NOT_READY` until all of the following are evidence-backed:

- zero P0 findings;
- Track A passes with no unexplained canonical-state divergence;
- Real QQ/NapCat isolated smoke passes with exact target verification;
- Real Provider smoke passes with safe failure behavior;
- restart/recovery passes for Task/Reminder, Agent, OneBot, API, and SQLite;
- backup/restore corruption and rollback cases pass;
- browser offline/reconnect refresh repairs canonical state;
- 30-minute soak passes and 6-hour candidate soak has no unbounded growth or unhandled task;
- secret/PII scan, `git diff --check`, compile check, and targeted regressions pass after any authorized fix;
- External ChatGPT reviews the evidence and changes the gate explicitly.

## 5. Bug-fix rule

This plan authorizes diagnosis and evidence collection only. A code change is allowed before external review only for a reproduced P0 involving data destruction, secret leakage, or an unintended external send. Any P1/P2 fix requires a new narrow authorization, a regression test for the reproduced failure, and a fresh handoff update. Do not change tests merely to make a failing scenario green.

## 6. Required evidence package

Each scenario records:

```text
scenario id
environment and disposable resource identifiers (redacted)
start/end canonical fact snapshot
fault injection point
outbound frames, if any (target redacted but identity-checkable)
observed error classification
restart/recovery result
logs and metric deltas
pass/fail/needs-reproduction decision
```

The package is reviewable without relying on chat memory. Until that package exists, `M7 FINAL` may remain PASS while `DAILY-USE CANDIDATE` remains NOT_READY.
