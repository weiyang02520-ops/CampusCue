# Design: CampusCue M7.1 First-use Activation

Date: 2026-08-22
Status: approved by the M7.1 execution brief; implementation pending

## Goal

Connect the existing source, AI-first extraction, canonical task, provenance,
and source-scoped Agent read paths into a first-use experience that is clear
without introducing a second connector, a new onboarding route, a schema
change, or production reminder delivery.

## Source-truth decisions

The audit found the required canonical capabilities already exist:

| Contract item | Actual support | Reuse | Gap/action |
|---|---|---|---|
| Source create/update/enable | `SourceService`, `/sources`, `/sources/{id}` | Yes | Add only activation copy |
| Connection test | `/sources/{id}/test` reads runtime adapter status | Yes | Add actionable failure/disabled copy |
| Deterministic injection | `TaskPipeline.handle(CampusEvent)` in integration tests | Yes | Add test-only provider/event fixture |
| Extraction outcome/confidence | `Extraction` row and message APIs | Yes | Present existing fields |
| Provenance | task `source_id`, `source_message_id`, `source_text_reference`; extraction audit | Yes | Add compact UI summary |
| Canonical task status | `TaskStatus.PENDING_CONFIRM` is present in model, DB constraint, service, API, and WebUI | Yes | Reuse status as Needs Review |
| Agent source scope/read tools | trusted `ToolContext` plus `task_list`/`task_get` | Yes | Add named isolation/tool-trace tests |
| Reminder facts | existing read-only reminder API and delivery interface | Yes | Add fake-boundary test only |

No M7.1 API, DB column, enum, migration, production connector, or reminder
delivery wiring is required.

## Implementation shape

1. Add an activation guide to the existing Home page. Its states are derived
   from loaded sources, messages, and tasks. It links to `/connections` and
   `/agent`; it never stores a local “completed” flag.
2. Reuse the Connections page and its existing test action. Make the empty,
   disabled, and failed states explain the next action, and keep test results
   scoped to the source that was tested.
3. Add a small `ProvenanceSummary` presentation component. Reuse it in task
   rows and message detail/list surfaces. It shows source identity, message
   reference/evidence availability, and product-language trust state without
   dumping audit JSON or secrets.
4. Preserve existing M6 tokens and theme architecture. New CSS uses existing
   semantic tokens and responsive layout rules, with no navigation or page
   redesign.
5. Keep Agent activation manual. The CTA fills or navigates to the existing
   Agent surface; it does not submit a request automatically.
6. Add test-only deterministic fixtures that call the real pipeline with a
   provider double, then exercise the existing canonical Agent tools. No
   production fixture branch is added.

## Failure and privacy behavior

- No source: explain that a source must be connected and link to Connections.
- Disabled source: explain that it must be enabled before extraction/Agent use.
- Adapter test failure: show a safe category/message and a retry or enable
  action; do not expose URLs, tokens, credentials, or tracebacks.
- Missing deadline: show “截止时间未识别/待补充”; never fabricate a date.
- `pending_confirm`: show “需要确认” and retain the existing canonical status;
  no new confirmation framework is built.
- Source isolation failures are a hard stop for the M7.1 gate.

## Test plan

Backend file: `v2/tests/integration/test_m71_first_use_activation.py`

- M7-A01 source creation and enablement
- M7-A02 disabled/disconnected connection UX facts
- M7-A03 official fixture through `CampusEvent` → `TaskPipeline` → SQLite
- M7-A04 uncertain fixture with no invented deadline
- M7-A05 task/extraction provenance projection
- M7-A06 canonical task tool call before Agent answer
- M7-A07 cross-source task isolation
- fake reminder delivery observer boundary, explicitly not production QQ

Frontend file: `v2/web/tests/e2e/m71-first-use-activation.spec.ts`

- activation guide states and actionability
- provenance/trust language
- source-scoped test result
- disabled/failed source copy
- 1440/390 layout smoke and all three visual-style regressions

Verification will run focused tests first, then the existing full V2 suite,
fresh installed package checks, frontend typecheck/build/Vitest/Playwright,
compileall, Anti-AstrBot, secret/PII scan, and `git diff --check`.

## Explicit non-goals

- No production QQ/NapCat reminder delivery (M7.2).
- No Agent memory, planning, multi-step product expansion, or new connector.
- No Schema/API redesign and no M6 theme/layout redesign.
- No claim that the complete five-minute E2E or M7 is complete.
