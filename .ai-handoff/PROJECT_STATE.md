# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy frozen/reference

## current_milestone

- M0-M4：**FINAL PASS**（M4 External ChatGPT 审核通过）
- M5 FINAL = PASS (External ChatGPT review completed before M6 authorization)
- M5.1.1 route cleanup = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW (historical implementation checkpoint)
- M6 = CHANGES_REQUESTED (External integration review)
- M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW (baseline)
- M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW (previous visual baseline)
- M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW
- M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS（方向与材质成立）
- M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- GLASS FINAL = NOT YET DECLARED
- DARK REVIEW = PENDING；NEUMORPHISM REVIEW = PENDING
- M6 FINAL = NOT YET DECLARED
- M7 = NOT_AUTHORIZED

## completed

- M1-M4 完整（含真实 QQ E2E）。
- **M5 API + Realtime（本轮）**：FastAPI `/api/v1` REST + SSE；Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System；Backup/Restore/Import/Export；Auth；Runtime lifecycle；RealtimeHub notifier 注入；schema v3（settings + sources.deleted_at + indexes）；contract/integration tests + fresh installed package。
- **M5.1.1 Final SSE Route Cleanup（本轮）**：HTTP stream outer generator 在客户端于 `: connected` 后立即断开、尚未进入 `hub.stream()` 时也会执行 unsubscribe cleanup。
- **M5.1 Final Hardening（本轮）**：SSE overflow now closes the active stream; configured heartbeat is consumed; Uvicorn startup has a readiness barrier and rollback; duplicate system health route removed; Adapter emits neutral `connection.updated`; realtime publish failures are isolated after committed mutations.
- **M6.1 WebUI integration hardening（本轮）**：修复 canonical task status、命名 SSE 消费与鉴权、Settings/System API 接线、真实日历/筛选/CRUD/编辑/删除/测试/导入导出/Agent source selector；加入真实 FastAPI+SQLite+RealtimeHub+local fake provider harness 与真实 Playwright integration。
- **M6.2 Subtle Visual Polish（本轮）**：保留现有 IA、布局和 API contract；通过 design tokens、surface hierarchy、teal accent、状态点、deadline/category 层级、brand mark、hover/focus/micro-motion 完成轻量视觉精修；Agent 去除机器人图标；生成独立 `.ai-handoff/visual/m62/` 与 dark evidence。
- **M6.2.1 Final Product Detail Cleanup（本轮）**：完成 Home 动态日期/时区与 action 分离、移动端 More bottom sheet、canonical priority、共享中文标签、theme icon 修正、topbar 假头像移除；生成独立 `.ai-handoff/visual/m621/` 与 `.ai-handoff/visual/m621-dark/`。
- **M6.3 Visual Character Pass（本轮）**：保留 M6.2.1 结构与业务 contract；以 Cue Line + Cue Dot、section tint、页面 identity、空状态、Tasks/Agent/Calendar/Home 节奏和 Messages/Connections/Providers/Settings 细节完成 distinctive product polish；生成 `.ai-handoff/visual/m63/` 与 `.ai-handoff/visual/m63-dark/`。
- **M6.4 Information Layering Pass（本轮）**：保持 M6.3 visual language，完成 Tasks/Agent/Messages 优先的信息分层，并收口 Calendar/Connections/Providers/Settings；新增 `.ai-handoff/visual/m64/` 与 `.ai-handoff/visual/m64-dark/`，不改 backend/API/business logic。
- **M6.5 Visual Depth & Product Composition（本轮）**：完成页面构图、surface hierarchy、字体比例、局部玻璃拟态和明暗/响应式收口；新增 `.ai-handoff/visual/m65/` 与 `.ai-handoff/visual/m65-dark/`，不改 backend/API/business logic。
- **M6.5.1 REAL Glassmorphism Correction（本轮）**：在 M6.5 HEAD 上只返工 App Shell/Home/Tasks/Agent 的真实 Glass material；新增连续 Atmospheric Canvas、分级 glass tokens、test-only marker verification 和 `.ai-handoff/visual/m651/glass/`，不扩张其他主题。
- **M6.5.2 Glass Refinement & Productization（本轮）**：按外部 Glass PASS 收口 backdrop、semantic material tiers、Agent utility/composer、Home empty state、Tasks toolbar/context/ISO date、mobile separation；新增 `.ai-handoff/visual/m652/glass/`，不改 backend/API/store/router/schema/business logic。

## verified (Workspace Agent local evidence)

- Full V2 pytest：**488 passed**（fresh installed-package `.venv-m511fresh` non-editable）
- M5/M5.1/M5.1.1 focused：**24 passed**；本轮新增 focused test **1 passed**
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS
- uvicorn local HTTP smoke PASS（health/task CRUD/reminders/backup）
- Runtime readiness smoke PASS（real localhost health + occupied-port rollback）；SSE lifecycle/heartbeat focused integration PASS。
- These are local Workspace Agent results, not independent External ChatGPT execution。
- M6.1 WebUI：typecheck PASS；production build PASS；Vitest 2 passed；Playwright full **12 passed**（含真实 M5 integration 与页面级证据）；axe violations 0；baseline 截图位于 `.ai-handoff/visual/m61/`。
- M6.2 visual polish：typecheck/build/unit PASS；Playwright full **12 passed**；light screenshots 位于 `.ai-handoff/visual/m62/`；dark evidence 位于 `.ai-handoff/visual/m62-dark/`；m61 baseline 保持未覆盖。
- M6.2.1：typecheck PASS；Vitest **4 passed**；focused Playwright **12 passed**；axe 0；m621 light/dark screenshot capture PASS；m61/m62/m62-dark evidence 未覆盖。
- M6.3：typecheck/build PASS；Vitest **4 passed**；focused Playwright **12 passed**；axe 0；real integration two tests individually PASS；m63 light/dark screenshot capture PASS；m61/m62/m621 evidence 未覆盖。
- M6.4：fresh installed-package `.venv-m64fresh` full V2 **488 passed**；typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**；m64 light/dark screenshot capture PASS；prior evidence preserved。
- M6.5：typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**；m65 light/dark screenshot capture PASS；prior evidence preserved。
- M6.5.1 Glass：typecheck/build PASS；focused Playwright **16 passed**；Glass material test **1 passed**；axe 0；m651 core evidence PASS；prior m65/m64 evidence preserved。
- M6.5.2 Glass：typecheck/build PASS；Vitest **4 passed**；focused refinement **2 passed**；M6 focused **16 passed**；M6.5.1 regression **1 passed**；real integration **2 passed**；fresh V2 **488 passed**；axe 0；responsive overflow/console/theme/fallback PASS；Stage 1 evidence `.ai-handoff/visual/m652/glass/`；m651 evidence restored from annotated baseline tag。

## real_environment

- M4 Real Provider Tool Call PASS；M4 Real QQ Agent E2E PASS
- M5 local real HTTP smoke PASS（无 QQ/NapCat 依赖）

## known_limitations

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh。

## next_gate

External visual review of M6.5.2 Stage 1 Glass evidence against the M6.5.1 baseline。GLASS FINAL、DARK REVIEW、NEUMORPHISM REVIEW and M6 FINAL must not be declared by this checkpoint；M7 remains unauthorized。

## architecture_decisions

- ADR-001 ~ ADR-013 + M4/M5 decisions in `.ai-handoff/DECISIONS.md` / docs。
