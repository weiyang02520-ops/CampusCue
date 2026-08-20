# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy frozen/reference

## current_milestone

- M0-M4：**FINAL PASS**（M4 External ChatGPT 审核通过）
- M5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5.1 hardening = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5.1.1 route cleanup = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M5 FINAL = NOT YET DECLARED
- M6 = NOT_AUTHORIZED

## completed

- M1-M4 完整（含真实 QQ E2E）。
- **M5 API + Realtime（本轮）**：FastAPI `/api/v1` REST + SSE；Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System；Backup/Restore/Import/Export；Auth；Runtime lifecycle；RealtimeHub notifier 注入；schema v3（settings + sources.deleted_at + indexes）；contract/integration tests + fresh installed package。
- **M5.1.1 Final SSE Route Cleanup（本轮）**：HTTP stream outer generator 在客户端于 `: connected` 后立即断开、尚未进入 `hub.stream()` 时也会执行 unsubscribe cleanup。
- **M5.1 Final Hardening（本轮）**：SSE overflow now closes the active stream; configured heartbeat is consumed; Uvicorn startup has a readiness barrier and rollback; duplicate system health route removed; Adapter emits neutral `connection.updated`; realtime publish failures are isolated after committed mutations.

## verified (Workspace Agent local evidence)

- Full V2 pytest：**488 passed**（fresh installed-package `.venv-m511fresh` non-editable）
- M5/M5.1/M5.1.1 focused：**24 passed**；本轮新增 focused test **1 passed**
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS
- uvicorn local HTTP smoke PASS（health/task CRUD/reminders/backup）
- Runtime readiness smoke PASS（real localhost health + occupied-port rollback）；SSE lifecycle/heartbeat focused integration PASS。
- These are local Workspace Agent results, not independent External ChatGPT execution。

## real_environment

- M4 Real Provider Tool Call PASS；M4 Real QQ Agent E2E PASS
- M5 local real HTTP smoke PASS（无 QQ/NapCat 依赖）

## known_limitations

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh。

## next_gate

External ChatGPT independent review of the pushed M5.1.1 checkpoint。M5 FINAL must not be declared by this checkpoint。

## architecture_decisions

- ADR-001 ~ ADR-013 + M4/M5 decisions in `.ai-handoff/DECISIONS.md` / docs。
