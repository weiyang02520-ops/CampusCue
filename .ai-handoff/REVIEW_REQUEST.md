# REVIEW_REQUEST.md

# CampusCue M5 API + Realtime Checkpoint — External Review Request

## Gate state

- M4 FINAL = **PASS**
- M5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5.1.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5 FINAL = NOT YET DECLARED
- M6 = NOT_AUTHORIZED

## What was implemented

- FastAPI REST `/api/v1` for Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System + Health/Status/Logs.
- SSE `/api/v1/stream` with bounded RealtimeHub; services publish through optional notifier.
- Schema v3: settings table, sources.deleted_at (soft delete preserving provenance), M5 indexes; atomic v1→v2→v3 migration.
- Backup/Restore/Import/Export; auth; runtime API lifecycle.
- M5.1 hardening: real SSE stream termination on overflow, configured heartbeat wiring, Uvicorn readiness/rollback, canonical health route cleanup, neutral `connection.updated` producer, and notifier exception isolation after commit.
- M5.1.1 route cleanup: outer HTTP SSE generator unsubscribes in `finally` for early consumer close after `: connected`.

## Local evidence (Workspace Agent only)

- Full V2 pytest: **488 passed** (fresh installed-package `.venv-m511fresh` non-editable)
- M5/M5.1/M5.1.1 focused: **24 passed**; M5.1.1 new test: **1 passed**
- compileall PASS; Anti-AstrBot PASS; git diff --check PASS; Secret/PII scan PASS
- uvicorn local HTTP smoke PASS (health/task CRUD/reminders/backup)
- local HTTP/SSE readiness smoke PASS; occupied-port startup failure and rollback PASS
- These results are local Workspace Agent evidence, not independent External ChatGPT execution。

## Not run / not touched

- M5 FINAL: NOT DECLARED
- M6: NOT_AUTHORIZED
- No real QQ/NapCat re-verification was needed; M4 real E2E remains valid.
- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are included.

## Known limitation / design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains; M5 schema v3 does not change it.
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted.
- SSE no-replay; clients must REST refresh after reconnect.

## External review focus

- Please independently verify the actual pushed source for SSE lifecycle termination, heartbeat consumption, API readiness barrier, canonical health route, event producer/commit ordering, and backup/restore/error-contract regressions.
