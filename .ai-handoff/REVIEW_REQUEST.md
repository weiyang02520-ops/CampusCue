# REVIEW_REQUEST.md

# CampusCue M6 WebUI Checkpoint — External Review Request

## Gate state

- M4 FINAL = **PASS**
- M5 FINAL = PASS（External ChatGPT）
- M6 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW
- M6 FINAL = NOT YET DECLARED
- M7 = NOT_AUTHORIZED

## M6 scope

- `v2/web/` is a Vue 3 + TypeScript + Vite frontend with Vue Router, Pinia, and Lucide icons.
- Implemented product areas: Home, Tasks, Messages, Calendar, Agent, Connections, Providers, Settings.
- M5 REST integration is canonical for loads and mutations; SSE is notification-only and reconnects with exponential backoff before REST refresh.
- Agent `tool_activity` is rendered only when returned by M5; the current backend returns an empty list, so the UI does not fake tool activity.
- Light/dark tokens, mobile bottom navigation, desktop sidebar, keyboard-visible focus, labeled controls, safe empty/error states, optimistic task completion rollback, and no-emoji UI.

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
- WebUI typecheck PASS；production build PASS；Vitest 2 passed；Playwright 9 passed；axe violations 0；responsive screenshots generated for 390/599/768/1024/1440 under `.ai-handoff/visual/m6/`。

## Not run / not touched

- M5 FINAL: PASS
- M6 FINAL: NOT YET DECLARED pending visual review
- M7: NOT_AUTHORIZED
- No real QQ/NapCat re-verification was needed; M4 real E2E remains valid.
- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are included.

## Known limitation / design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains; M5 schema v3 does not change it.
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted.
- SSE no-replay; clients must REST refresh after reconnect.

## Visual review focus

- Please independently inspect the pushed screenshots and source at the five required viewport widths. Focus on hierarchy, density, mobile bottom navigation, task/date readability, dark mode parity, responsive overflow, and whether the calm student-workspace direction is visually coherent. **VISUAL REVIEW REQUIRED BY EXTERNAL MODEL. M6 FINAL must not be declared from local evidence alone.**
