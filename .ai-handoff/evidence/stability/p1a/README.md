# CampusCue P1A Stability Evidence

Date: 2026-08-22

Gate: `POST-M7 P1A SAFETY & DATA INTEGRITY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`

Scope: disposable SQLite, synthetic data, Fake NapCat, local/fake provider, and a controlled CampusCue worker process. No real QQ, real provider, production database, or production identifiers were used.

## Results

### REL-P1-002 — SQLite lock and commit failure

- Before: disposable database contained the canonical baseline rows.
- Fault: a second connection held a SQLite write lock, and one commit path was injected to fail.
- Observed: the write returned a classified failure; no half-created Task, Extraction, or Reminder row appeared; failed mutation did not partially update an existing Task; the session remained usable.
- After: canonical snapshot matched the pre-fault snapshot.
- Recovery: a fresh repository operation succeeded against the same disposable database.
- Side-effect count: zero on failed attempts; one on the explicit successful retry.
- Result: `PROVEN_SAFE`.

### REL-P1-003 — Task to Reminder crash gap

- Before: a pending Task with a deadline was the canonical fact.
- Faults: injected boundary failures before planning, after partial fact work, and during scheduler derivation; an existing-reminder cancellation gap was also exercised.
- Observed: the Task remained present; no duplicate active reminder facts were created; stale facts were cancelled where required.
- After: the canonical Task/Reminder state converged to the policy result.
- Recovery: restart-equivalent `resync_all()` rebuilt only the derived scheduler state and remained idempotent.
- Side-effect count: each logical reminder was present at most once; no outbound delivery was used.
- Result: `PROVEN_SAFE` within the supported single-runtime recovery boundary.

### REL-P1-004 — Backup/Restore failure and success

- Before: a disposable database contained a logical canonical snapshot.
- Faults: malformed/incompatible restore payloads and restore failure paths were exercised.
- Observed: failed restore left the canonical snapshot unchanged and did not resync derived state.
- After: a valid restore replaced the intended logical rows only after commit.
- Recovery: scheduler reconciliation ran after successful replacement.
- Side-effect count: zero for failed restores; one committed replacement for the valid restore.
- Result: `CONFIRMED BUG -> FIXED` for the reproduced SQLite foreign-key ordering defect. `SystemService.restore` now flushes parent rows before child rows under SQLite foreign-key enforcement.

### REL-P1-005 — OneBot reconnect/action generation

- Before: Fake NapCat A had one in-flight action.
- Fault: Fake NapCat B replaced A; A's delayed echo was sent on B before B's own response.
- Observed: A's stale echo did not resolve B's pending action; B's action resolved exactly once; pending actions returned to zero.
- After: the runtime stopped cleanly with no pending action leak.
- Recovery: a new Fake NapCat connection remained usable.
- Side-effect count: one action for A and one action for B; no duplicate action from the stale echo.
- Result: `PROVEN_SAFE` for the local adapter generation boundary. Real QQ/NapCat deployment remains unauthorized and unrun.

### REL-P1-008 — Forced stop and restart recovery

- Before: a controlled CampusCue worker committed one synthetic Task to a disposable database.
- Fault: the worker was stopped once with `terminate` and once with `kill` while its runtime was active.
- Observed: the process exited; the database reopened without schema refusal or lock residue.
- After: the Task remained exactly once.
- Recovery: a new service instance ran `resync_all()` successfully.
- Side-effect count: one canonical Task; zero outbound sends.
- Result: `PROVEN_SAFE` for the controlled worker scope. A real deployment soak remains unrun.

### Agent/Web concurrency boundaries

- Concurrent confirmation: one pending mutation proposal was consumed; exactly one Task update committed; the second confirmation did not execute a second write.
- Same-thread turns: the second provider turn waited for the first and the conversation retained ordered user messages.
- Cross-source request: a concurrent request using another source was rejected before history/provider access.
- Browser stale response: a delayed response from the previous source was not rendered after source switching; the new source response rendered normally.
- Result: `PROVEN_SAFE` for the tested local Agent/Web boundaries.

## Verification totals

- P1A focused storage/runtime/Agent: `17 passed`
- Full V2 from source tree: `530 passed`
- Fresh non-editable installed-package full V2: `530 passed`
- Web typecheck/build: `PASS`
- Web Vitest: `4 passed`
- Full Chromium E2E: `42 passed`
- compileall: `PASS`
- Anti-AstrBot: `PASS`
- secret/PII scan: `PASS` (no secret-pattern hits in V2; numeric identifiers are synthetic fixtures)
- `git diff --check`: `PASS`

## Explicitly not run

Real QQ/NapCat, Real Provider, multi-runtime/shared-database claims, SSE replay, durable Agent memory, soak testing, and M8 work remain outside this authorization.
