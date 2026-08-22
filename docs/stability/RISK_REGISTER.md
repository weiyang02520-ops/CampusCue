# CampusCue Post-M7 Risk Register

> Status: audit complete, awaiting External ChatGPT review  
> Baseline: `143e85fb2511071d3fcf1e4d6040a3546cd70c2b`  
> This register records risks and proof gaps, not newly discovered source defects.

## Severity rules

- **P0**: immediate data destruction, secret exposure, or an unintended external send. Stop and fix before any other work.
- **P1**: could corrupt canonical state, lose an important user action, misdeliver a reminder, or block trustworthy daily use. Requires reproduction before daily-use candidacy.
- **P2**: recoverable reliability, UX, scale, or observability gap. Must have a bounded follow-up but does not authorize M8.

## Register

| ID | Severity | Risk / failure mode | Current protection and evidence | Reproduction plan | Recommended follow-up | Daily-use blocker |
|---|---|---|---|---|---|---|
| REL-P1-001 | P1 | Real QQ/NapCat delivery has not been independently exercised after M7.2; wrong target, account permission, or deployment mismatch is therefore unproven | Source-bound resolution, strict OneBot GROUP checks, Fake NapCat exact-target path; Real QQ = `NOT_RUN` | Disposable QQ account/group, explicit source row, capture outbound group/message and resulting Reminder row | Run isolated real QQ smoke; do not add a new channel or change the contract | YES |
| REL-P1-002 | P1 | SQLite lock/commit failure during concurrent extraction/task writes has no dedicated fault-injection proof | SQLAlchemy transactions, busy timeout, rollback on repository errors; no targeted locked-writer matrix | Hold a write lock on a disposable DB; inject failures before/at commit; compare task/extraction/reminder facts | Define retry/no-retry behavior and add regression tests only after observed behavior is classified | YES |
| REL-P1-003 | P1 | Task and Reminder are committed through separate repository operations; a crash between them can leave a temporary derived-fact gap | `resync_all()` explicitly heals the simulated planning-died gap; atomicity remains a known M3 limitation | Inject process termination/exception after task commit at each planning step, then restart with same DB | Keep Task as canonical; prove recovery and document any user-visible window before changing design | YES |
| REL-P1-004 | P1 | Logical restore has basic round-trip coverage but corrupt-row, FK, duplicate-key, and commit-failure safety are not fully exercised | SystemService validates top-level shape and wraps replacement in one transaction; scheduler resync follows commit | Restore variants on a disposable copy; inject failure during flush/commit; assert byte-level logical facts before/after | Harden validation or transaction boundary only from a reproduced failure | YES |
| REL-P1-005 | P1 | NapCat reconnect can overlap a reminder delivery or in-flight action; local adapter races are covered, real timing is not | Connection generations fail stale pending actions; reminder delivery checks current connection and records safe error | Disconnect/replace WS during action and during reminder fire; assert no duplicate or wrong target | Add the smallest regression at the failing boundary; no automatic retry without a product decision | YES |
| REL-P1-006 | P1 | Semantic duplicate messages with new message IDs can still produce ambiguous behavior for compound/forwarded announcements | M2 semantic dedup and source-message unique key are tested; M4 limitation is documented | Replay edited/forwarded/compound campus notices with distinct IDs and compare expected task cardinality | Product decision first: split policy vs one-message-one-task contract | YES for ingestion expansion |
| REL-P1-007 | P1 | Real Provider extraction/Agent behavior may differ from MockTransport/fake provider behavior under latency, rate limits, or endpoint-specific output | Provider taxonomy, structured output fallback, malformed output and Agent bounds are locally covered; Real Provider smoke = `NOT_RUN` | Use a disposable provider configuration and safe prompt; inject timeout/429/malformed responses at a controllable proxy | Record safe UX, no fabricated task, and no secret/body leakage before considering code changes | YES for public demo |
| REL-P1-008 | P1 | Hard stop/restart while active bus handlers, scheduler callbacks, WS actions, or DB sessions are running is not a proven production sequence | Bounded shutdown, API startup rollback, bus drain/cancel, scheduler-before-adapter ordering are implemented and locally tested | Run controlled SIGTERM and forced-stop matrix with active work; inspect DB and task counts after restart | Fix only a reproduced orphan, duplicate, or lost canonical mutation | YES |
| REL-P2-001 | P2 | SSE has no replay; a client can miss a notification during a disconnect | Contract says notification-only and `useSse` refreshes REST after reconnect; early route close is tested | Toggle browser offline/API restart while committing a task; assert refresh repairs the UI | Keep notification-only contract; improve evidence/metrics before considering replay | NO, if REST refresh is proven |
| REL-P2-002 | P2 | Reminder duplicate-fire guard is process-local; two runtime processes sharing a DB are outside the current single-runtime architecture | `asyncio.Lock` covers sequential/concurrent callbacks in one process; no distributed claim | Start two runtimes against a disposable shared DB and race the same reminder | Keep single-runtime deployment boundary or design a DB claim before multi-instance support | NO for supported single runtime; YES for multi-instance |
| REL-P2-003 | P2 | Agent conversation and pending approvals are in memory and disappear on restart | Restart clearing and source/thread binding are intentional and tested | Restart during pending confirmation; verify no mutation and clear UX | Do not add durable memory/approval storage without a new product authorization | NO |
| REL-P2-004 | P2 | Frontend offline, slow-response, and refresh-race behavior has not been adversarially tested in this audit | M6 Chromium baseline, reconnect backoff, REST refresh, offline/reconnecting states | Browser network throttling, aborts, duplicate clicks, and delayed SSE/REST responses | Add focused browser regression only for an observed stale or falsely committed state | NO pending proof |
| REL-P2-005 | P2 | Operational telemetry does not yet prove queue depth, open WS, subscriber count over time, Agent thread count, DB size, or unhandled task count | Bounded data structures, system status, redacted log buffer, prior secret/PII scan | 30-minute and 6-hour soak with periodic snapshots and log scan | Define minimum daily-use metrics and thresholds before public deployment | YES for daily-use candidate |

## Counts at this gate

- Confirmed P0 bugs: **0**
- P1 risks requiring reproduction: **8**
- P2 risks requiring bounded follow-up: **5**
- No risk is authorized to expand M7 into M8.

## Immediate stop conditions

If any test demonstrates an unintended external send, cross-source data, secret/PII output, or canonical task loss, stop the matrix, preserve the disposable evidence, and open a narrowly scoped P0 fix. Do not mask the failure with a test-only change or broad refactor.
