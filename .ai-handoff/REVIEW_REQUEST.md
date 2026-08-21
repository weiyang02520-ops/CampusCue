# REVIEW_REQUEST.md

# CampusCue M6.5.3 Dark UI Stage 1 — External Review Request

## Current checkpoint

- M6.5.2 Glass baseline tag: `m6.5.2-glass-baseline` → `63d7aeb4177b61bc73bffa336d6743e50c780559`。
- M6.5.2 Glass remains **IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**。
- M6.5.3 Dark is **IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**。
- Dark Final、Glass Final、M6 Final are **NOT YET DECLARED**；Neumorphism is **PENDING**；M7 is **NOT_AUTHORIZED**。

## M6.5.3 Dark Stage 1 review target

Review `.ai-handoff/visual/m653/dark/` at 1440 and 390 widths. Dark is intentionally an independent solid-surface productivity workspace, not Glass Dark: no large backdrop blur, transparent glass panels, atmospheric cyan gradients, or white edge highlights.

Focus on low-glare hierarchy and information density: Today direct content, blue Week Focus, flat Upcoming rows, raised neutral Messages, teal AI context, raised Tasks toolbar, flat task rows, deep neutral Agent conversation, raised composer, dark Settings controls, and the visible Glass/Dark selector. Confirm the mobile bottom nav is solid/raised and the Agent composer is not obscured. Do not advance to Stage 2, Neumorphism, Dark Final, M6 Final, or M7 from this local checkpoint.

Evidence: `dark-shell-1440.png`, `dark-home-1440.png`, `dark-tasks-1440.png`, `dark-agent-1440.png`, `dark-settings-1440.png`, `dark-home-390.png`, `dark-agent-390.png`。

## Gate state

- M4 FINAL = **PASS**
- M5 FINAL = PASS（External ChatGPT）
- M6 = CHANGES_REQUESTED（External integration review）
- M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW（previous visual baseline）
- M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW
- M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS（方向与材质成立）
- M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- GLASS FINAL = NOT YET DECLARED；DARK REVIEW = PENDING；NEUMORPHISM REVIEW = PENDING
- M6 FINAL = NOT YET DECLARED
- M7 = NOT_AUTHORIZED

## M6.2 scope

- `v2/web/` is a Vue 3 + TypeScript + Vite frontend with Vue Router, Pinia, and Lucide icons.
- Implemented product areas: Home, Tasks, Messages, Calendar, Agent, Connections, Providers, Settings.
- M5 REST integration is canonical for loads and mutations; SSE is notification-only and reconnects with exponential backoff before REST refresh.
- Agent `tool_activity` is rendered only when returned by M5; the current backend returns an empty list, so the UI does not fake tool activity.
- Light/dark tokens, mobile bottom navigation, desktop sidebar, keyboard-visible focus, labeled controls, safe empty/error states, optimistic task completion rollback, and no-emoji UI.
- Canonical task statuses are `pending_confirm | pending | done | dismissed`; no frontend `completed` status.
- Authenticated fetch-based SSE consumes named M5 events and triggers canonical REST refresh; token is sent in `Authorization`, never in the URL.
- Settings/System uses the actual M5 allowlist and endpoints. Tasks, Calendar, Messages, Connections, Providers and Agent source selection use real API contracts.
- M6.2 changes only shared visual tokens, CSS and small presentation-level icon/metadata markup; IA, API, store, router, backend and schema are unchanged.
- M6.1 baseline tag: `m6.1-ui-baseline`; baseline screenshots remain under `.ai-handoff/visual/m61/`.

## What was implemented

- FastAPI REST `/api/v1` for Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System + Health/Status/Logs.
- SSE `/api/v1/stream` with bounded RealtimeHub; services publish through optional notifier.
- Schema v3: settings table, sources.deleted_at (soft delete preserving provenance), M5 indexes; atomic v1→v2→v3 migration.
- Backup/Restore/Import/Export; auth; runtime API lifecycle.
- M5.1 hardening: real SSE stream termination on overflow, configured heartbeat wiring, Uvicorn readiness/rollback, canonical health route cleanup, neutral `connection.updated` producer, and notifier exception isolation after commit.
- M5.1.1 route cleanup: outer HTTP SSE generator unsubscribes in `finally` for early consumer close after `: connected`.

## External findings addressed in M6.1

- `completed`/`done` mismatch; named SSE event delivery; Settings fake `language` field and missing System methods.
- Hardcoded Calendar dates; missing task API filters, CRUD/editor/delete/deadline clear; missing Messages detail/filters/retention; incomplete Connections/Providers test/toggle/delete; missing Agent source selector.
- Mock-only Playwright coverage replaced with a real isolated M5 FastAPI + SQLite + RealtimeHub harness and deterministic local fake provider upstream.

## M6.2 visual polish

- Quiet premium blue-slate direction retained; added restrained teal accent only for AI/source/calendar/status semantics.
- Added surface hierarchy, Today accent line, focus-day indicator, neutral task category chips, deadline urgency tones, message status rails/confidence bars, brand Sparkles mark, composer focus state, dialog/toast motion, and mobile active-nav indicator.
- No gradients, glassmorphism, neon, emoji, decorative images, robots, IA changes, or product rewrite.

## M6.2.1 product detail cleanup

- Home date/week and pending count derive from Settings timezone; upcoming tasks sort by deadline; complete and dismiss use separate request actions.
- Mobile nav is 总览/任务/日历/AI/更多；More opens an accessible bottom sheet for 消息/连接/模型提供商/设置 with Escape/backdrop close, focus restoration, and active-route state.
- Runtime frontend priority vocabulary is only `low | normal | high`; category/status/priority presentation uses shared Chinese labels；theme toggle icon/label semantics are corrected；fake topbar avatar is removed.
- New evidence is isolated under `.ai-handoff/visual/m621/` and `.ai-handoff/visual/m621-dark/`; `.ai-handoff/visual/m61/`, `m62/`, and `m62-dark/` are preserved.

## M6.3 visual character pass

- Baseline tag `m6.2.1-ui-baseline` points to the stable M6.2.1 HEAD; no prior m61/m62/m621 screenshots were overwritten.
- Cue Line + Cue Dot is used as a restrained CampusCue motif across page headers, task deadlines, calendar/task days, signal empty states, Agent, and sidebar rhythm.
- Home, Tasks, Agent, and Calendar received the primary pass; Messages, Connections, Providers, and Settings received the same empty-state, surface, status, source/provider, and section-rail language.
- Desktop whitespace is carried by the page background rather than stretched panels；Tasks overview uses real task data；Agent uses a barely visible CSS dot field；Mobile Agent composer sits above the bottom nav。
- No API, store, router, backend, schema, SSE, task logic, generated image, gradient, glassmorphism, neon, emoji, or marketing layout changes。

## Local evidence (Workspace Agent only)

- Full V2 pytest: **488 passed** (fresh installed-package `.venv-m511fresh` non-editable)
- M5/M5.1/M5.1.1 focused: **24 passed**; M5.1.1 new test: **1 passed**
- compileall PASS; Anti-AstrBot PASS; git diff --check PASS; Secret/PII scan PASS
- uvicorn local HTTP smoke PASS (health/task CRUD/reminders/backup)
- local HTTP/SSE readiness smoke PASS; occupied-port startup failure and rollback PASS
- These results are local Workspace Agent evidence, not independent External ChatGPT execution。
- WebUI typecheck/build PASS；Vitest **4 passed**；M6 focused Playwright **12 passed**；axe violations 0；real integration tests individually PASS；light/dark M6.3 evidence under `.ai-handoff/visual/m63/` and `.ai-handoff/visual/m63-dark/`。

## Not run / not touched

- M5 FINAL: PASS
- M6.1: IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW（baseline）
- M6.3: IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6 FINAL: NOT YET DECLARED pending external visual comparison
- M7: NOT_AUTHORIZED

## M6.5.2 Stage 1 review target

M6.5.1 Glass direction has passed external visual review. This checkpoint refines the material system without amplifying it: quieter backdrop, fixed semantic tiers (Base / Primary / Context / Raised / Floating), less opaque utility controls, direct Home Today empty content, readable Tasks rows with localized dates, and a calmer mobile Agent separation.

Review the new evidence in `.ai-handoff/visual/m652/glass/` against the preserved M6.5.1 evidence in `.ai-handoff/visual/m651/glass/`:

- `refine-home-1440.png` / `refine-home-390.png`
- `refine-tasks-1440.png`
- `refine-agent-1440.png` / `refine-agent-390.png`

Questions: Is the backdrop quieter while still making the material legible? Are Base/Primary/Context/Raised tiers visually coherent? Does information remain ahead of material? Are Home Today, Tasks overview/date, Agent utilities/composer, and mobile bottom navigation product-ready? **GLASS FINAL and M6 FINAL must remain undeclared until external review.**
- No real QQ/NapCat re-verification was needed; M4 real E2E remains valid.
- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are included.

## Known limitation / design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains; M5 schema v3 does not change it.
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted.
- SSE no-replay; clients must REST refresh after reconnect.

## Review focus

- Please compare `.ai-handoff/visual/m621/` against `.ai-handoff/visual/m63/`, and inspect `.ai-handoff/visual/m63-dark/`. Focus on whether the character pass adds hierarchy and recognizability without becoming decorative: Cue motif restraint, empty states, Tasks whitespace, Agent canvas/composer, Calendar scanability, mobile bottom-nav safety, dark-mode strength, and preserved product clarity. **EXTERNAL VISUAL REVIEW REQUIRED. M6 FINAL must not be declared from local evidence alone.**

## M6.4 visual review request

- M6.4 verification: fresh installed-package `.venv-m64fresh` full V2 **488 passed**；WebUI typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**；light/dark evidence under `.ai-handoff/visual/m64/` and `.ai-handoff/visual/m64-dark/`。
- Compare M6.4 against the `m6.3-ui-baseline` and M6.3 evidence. Focus on progressive disclosure: Tasks primary list vs context aside, Agent conversation vs context rail, Messages master/detail, mobile sheets, Calendar selected-day agenda, and advanced provider/connection/settings details。
- **M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M6.5 visual review request

- Baseline: `m6.4-ui-baseline` → `26392e633b1ab47bfe39c1831c774c638f9b7076`；compare `.ai-handoff/visual/m65/` and `.ai-handoff/visual/m65-dark/` against M6.4 evidence。
- Review page composition, canvas/section/raised surface hierarchy, Home/Tasks/Agent editorial grids, Agent context depth, Calendar scanability, Messages signal stream, Settings three-column navigation, 1024/768/390 behavior, and dark-mode contrast。
- Glassmorphism is intentionally local, not global: inspect Agent context/composer, Home focus, dialogs/inspectors and connection status; verify text remains clear and solid fallbacks are acceptable when `backdrop-filter` is unavailable。
- No backend/API/store/router/schema/business logic changes；dataset remains 5 tasks / 3 messages / 3 sources / 1 provider。
- **M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M6.5.1 Glass review request

- Starting HEAD: `524e4a13a2ba257fa5b04194219c17c9d6cd068c`；Glass evidence: `.ai-handoff/visual/m651/glass/`。
- First phase only: App Shell, Home, Tasks and Agent. Review `glass-shell-1440`, `glass-home-1440`, `glass-tasks-1440`, `glass-agent-1440`, `glass-home-390`, `glass-agent-390` and `glass-agent-marker-1440`。
- Hard checklist: Backdrop, Tint, Blur, Edge Light, Shadow, Text Contrast, Solid/Tinted Fallback. The test-only marker must remain perceptible through the Agent glass surface after tint + blur。
- Confirm the three-plane relationship: Atmospheric Backdrop → Glass Workspace/Context → opaque readable content → Raised Composer. Task rows/message bubbles/calendar cells must not become individually blurred。
- No Dark expansion, no Neumorphism expansion, no IA/data/API/store/router/backend/schema/business logic changes。
- **M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS**（historical direction gate）；**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**GLASS FINAL = NOT YET DECLARED**；**DARK REVIEW = PENDING**；**NEUMORPHISM REVIEW = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。
