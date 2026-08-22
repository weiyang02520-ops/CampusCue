# CampusCue Post-M7 Reliability Matrix

> Audit: POST-M7 P0 REAL-WORLD RELIABILITY AUDIT
> Audit date: 2026-08-22
> Baseline: `143e85fb2511071d3fcf1e4d6040a3546cd70c2b` (`HEAD == origin/main`)
> Scope: authorized P1A failure-injection tests and narrowly scoped recovery fix; no real QQ/provider, schema, API, replay, durable-memory, or M8 work.

## Gate

- `M7 FINAL = PASS`
- `POST-M7 P0 RELIABILITY AUDIT = PASS`
- `POST-M7 P1A SAFETY & DATA INTEGRITY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`
- `DAILY-USE CANDIDATE = NOT_READY`
- `M8 = NOT_AUTHORIZED`

This document distinguishes implementation evidence from real-environment proof. A `PARTIAL` row is not an observed production defect; it means an important boundary is implemented or locally tested but still lacks the requested failure injection, real integration, or soak evidence.

## System chain under audit

```text
OneBot/NapCat ingress
  -> converter / self-message suppression / transport dedup
  -> bounded EventBus
  -> TaskPipeline + Provider
  -> Extraction / TaskService / SQLite facts
  -> ReminderService facts -> derived scheduler -> delivery boundary
  -> REST canonical reads + notification-only SSE
  -> source-scoped Agent + explicit mutation confirmation
```

Canonical facts are SQLite rows. Scheduler jobs, SSE events, in-memory Agent conversations, pending approvals, and transport dedup entries are derived or process-local state and must not be treated as durable facts.

## Scenario matrix

| ID | Critical path / fault | Expected safe result and canonical state | Existing evidence | Status | Next proof |
|---|---|---|---|---|---|
| R-A01 | OneBot disconnect, reconnect, stale connection cleanup | Old connection cannot process frames or fail new pending actions; new connection can send | `test_fake_napcat.py`; `test_m11_regressions.py`; `test_connection_generation.py` | PARTIAL | Isolated real NapCat reconnect with an action in flight |
| R-A02 | Same event delivered again after reconnect | No second bus/pipeline action and no second task | Fake NapCat duplicate test; transport dedup unit tests | COVERED LOCALLY | Verify TTL expiry and process restart behavior in a controlled run |
| R-A03 | Same semantic announcement arrives with a different message ID | Semantic dedup prevents a second task when title/course/deadline match; known compound-message limitation remains explicit | `test_m2b1_units.py`; `test_m2b1_pipeline.py` | PARTIAL | Realistic message corpus with edits, forwarded notices, and compound announcements |
| R-A04 | Outbound action timeout, closed socket, non-zero retcode, duplicate echo | Safe `ActionFailure`; pending entry and semaphore are released; no unhandled task exception | `test_actions.py`; `test_fake_napcat.py`; protocol tests | COVERED LOCALLY | Action failure while runtime is shutting down |
| R-A05 | Event burst, queue saturation, handler exception, shutdown | Bounded backpressure; one handler failure does not kill dispatch; shutdown drains/cancels within bound | `test_bus.py`; `test_m11_fixes.py` | PARTIAL | 30-minute burst with counters for queue depth, dropped/drained work, and task leaks |
| R-A06 | Provider timeout, network error, 429, 5xx, malformed JSON/structured output | No task is fabricated; extraction records a safe provider error; Agent returns safe UX without raw body/secret | `test_provider.py`; `test_m2a1_fixes.py`; `test_m2b1_pipeline.py`; `test_m4_agent_loop.py` | PARTIAL | Real Provider smoke and controlled upstream fault responses |
| R-A07 | SQLite write failure, lock, or busy timeout during task/extraction mutation | Request fails safely; transaction rollback leaves no half-written canonical row; retry policy must not duplicate side effects | P1A disposable locked-DB and injected commit-failure tests | PROVEN_SAFE | Real multi-process/production soak remains outside scope |
| R-A08 | Task commit succeeds before reminder planning completes | Task remains canonical; startup `resync_all()` reconstructs missing reminder facts/jobs without churn | P1A boundary-fault and restart-equivalent resync tests | PROVEN_SAFE | Real deployment timing/soak remains outside scope |
| R-A09 | Process restart with scheduled, stale, missed, or inactive reminders | DB facts are reconciled; future valid jobs are rebuilt; missed jobs are not backfilled; done/dismissed tasks do not fire | `test_m3_reminders.py`; `test_m33_recovery.py` | PARTIAL | Real runtime stop/start with the same DB and wall-clock transition |
| R-A10 | Reminder callback fires twice concurrently | One process-local claim guard allows one delivery attempt; duplicate callback sees non-scheduled fact | M7.2 sequential/concurrent fire tests; M3 fire tests | PARTIAL | Two-process/shared-DB experiment; current guard is intentionally process-local |
| R-A11 | Reminder target disabled, deleted, missing, non-OneBot, malformed, or disconnected | Zero outbound send; safe `delivery:*` error in Reminder; task/source provenance unchanged | `test_m72_onebot_reminder_delivery.py`; source policy tests | COVERED LOCALLY | Real QQ target verification with a disposable test group |
| R-A12 | OneBot delivery reaches the wrong group or returns action failure | Target must resolve from `Task.source_id`; action uses existing adapter boundary; failure is recorded and not retried silently | M7.2 source-bound delivery code and Fake NapCat exact-target test | PARTIAL | Real QQ isolated group: assert target, exact message, and failure behavior |
| R-A13 | Agent thread reused under another source | Fail closed before old history/provider/tool use; pending mutation is cancelled; no cross-source data leak | M7.3 source-binding regression plus P1A concurrent-source test | PROVEN_SAFE | Long soak remains outside scope |
| R-A14 | Agent mutation proposal replayed, rejected, ambiguous, or confirmed after restart | Only explicit current confirmation executes frozen arguments; reject/ambiguous/restart/cross-source paths do not mutate | M7.3 tests plus P1A concurrent-confirmation test | PROVEN_SAFE | Real browser/network retry beyond targeted stale-response test remains outside scope |
| R-A15 | Agent provider/tool timeout, context overflow, duplicate tool loop, max-step exhaustion | Bounded safe response; no traceback or unbounded tool/provider loop; canonical task writes still use TaskService | `test_m4_agent_loop.py`; M4 tools/provider tests | PARTIAL | Resource/latency soak with real provider and concurrent threads |
| R-A16 | SSE client closes early, reconnects, or misses an event | Early close unsubscribes; SSE remains notification-only; reconnect performs REST refresh rather than assuming replay | `test_m5_realtime.py`; `useSse.ts`; M5 contract | PARTIAL | Browser offline/online and API restart run with explicit stale-state assertions |
| R-A17 | WebUI receives stale state, network failure, or refresh race | UI shows offline/reconnecting state and canonical REST reload repairs state; no optimistic mutation remains falsely committed | 42 Chromium tests plus P1A delayed-source-response test | PROVEN_SAFE_TARGETED | Broader offline/slow-response matrix remains outside scope |
| R-A18 | Backup malformed, incompatible, or restore commit fails | Validate before mutation; restore is one transaction; rollback preserves pre-restore facts; scheduler resync follows success only | P1A corrupt/failure/valid restore tests; explicit parent-before-child flush fix | CONFIRMED BUG -> FIXED | Real backup files and production restore remain outside scope |
| R-A19 | Runtime startup conflict, partial startup failure, graceful stop | API readiness is a real barrier; failure rolls back API/adapter/bus/DB; shutdown order prevents new ingress and waits bounded work | Existing runtime rollback tests plus P1A bounded stop/worker recovery | PROVEN_SAFE_CONTROLLED | Deployment soak remains outside scope |
| R-A20 | Long-running leak, log safety, and operational visibility | No unbounded queue/thread/subscriber/conversation growth; logs contain no secret/PII; health reflects component state | bounded structures, redacted log design, prior secret/PII scan | GAP | 30-minute minimum soak, then 6-hour daily-use candidate run with metrics snapshot |

## Evidence summary

- Local deterministic and fake integration evidence is strong for transport races, source binding, confirmation, reminder lifecycle, provider taxonomy, and SSE lifecycle.
- The largest unclosed boundary is real-world delivery: Real QQ E2E remains `NOT_RUN`; Fake NapCat does not prove target ownership, account permissions, or NapCat deployment behavior.
- The known M3 Task/Reminder cross-repository atomicity risk is a recovery design, not a claim of atomic commit. The current code relies on startup reconciliation after a crash gap.
- The known M4 `(source_id, source_message_id)` uniqueness contract is preserved. It is not a transport duplicate bug, but it can under-model compound announcements and needs a product decision before broad ingestion.
- SSE has no replay by design. Correctness depends on the REST refresh path after reconnect.

## Audit conclusion

No confirmed P0 data-loss, secret-leak, or wrong-external-send defect was found. One P1 restore defect was reproduced and fixed narrowly. Daily-use readiness remains `NOT_READY` because Real QQ/Provider and soak evidence are still explicitly unrun.
