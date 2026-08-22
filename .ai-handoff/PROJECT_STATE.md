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
- M6.5.3 DARK STAGE 1 = PASS
- M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW (Stage 2 implementation complete)
- GLASS FINAL = PASS
- M6.5.4 NEUMORPHISM = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW
- M6.5.4.1 THEME UX = PASS
- NEUMORPHISM MATERIAL = PASS
- GLASS FINAL = PASS；DARK FINAL = PASS；NEUMORPHISM FINAL = PASS
- M6 FINAL = PASS（CampusCue WebUI completed）
- M7 ROADMAP DESIGN = PASS
- M7.0 PRODUCT CONTRACT = PASS
- M7.1 FIRST-USE ACTIVATION = PASS
- M7.2 ONEBOT REMINDER DELIVERY = PASS
- M7.3 BOUNDED AGENT COPILOT = PASS
- M7 FINAL = PASS
- M7.4 = NOT NEEDED / NOT AUTHORIZED

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
- **M6.5.3 Dark UI Stage 1（本轮）**：以独立 solid-surface productivity language 完成 App Shell、Home、Tasks、Agent、Settings selector；新增 dark token system、Dark evidence 与 route-level visual regression；不改 backend/API/store/router/schema/business logic。基线 tag：`m6.5.2-glass-baseline`。
- **M6.5.3 Dark UI Stage 2（本轮）**：扩展 Calendar、Messages、Connections、Providers、Settings、Dialog、Bottom Sheet、Toast、Empty/Loading/Offline/Reconnecting，并补齐 1440/1024/390 evidence 与 Glass/Dark comparison；移除 Theme Selector CSS nth-child 文本伪装，`system` 正确跟随 `prefers-color-scheme`；不改 backend/API/store/router/schema/business logic。Stage 1 = PASS；Dark implementation complete awaiting external visual review。
- **M6.5.4 Neumorphism（本轮）**：新增前端独立 `data-visual-theme` 材质选择，与后端 `data-theme` 的 `system/light/dark` 外观契约分离；完成同材质 canvas、定向双阴影、raised/inset hierarchy、平坦高频内容层、Settings 风格选择器与全页面响应式 Neu implementation；不改 backend/API/schema/Agent/tasks logic/IA。
- **M6.5.4.1 Theme UX Cleanup（本轮）**：将用户选择收敛为单一 `system | glass | dark | neumorphism` 视觉风格；System 按 OS 解析为 Glass/Dark，显式三套材质不受 OS 变化影响；backend 仍只接收 `system/light/dark`，不发送 `neumorphism`。
- **M6 Final Closure Candidate（本轮）**：删除 Settings 旧 Appearance section、`themeOptions`、`appearance-picker` 及隐藏兼容 CSS；补充三主题全路由/响应式/可访问性回归与最终 candidate evidence `.ai-handoff/visual/m6-final-candidate/`；仅修复 Dark dialog description 的 WCAG 对比度边界，不改变材质、布局、API 或业务逻辑。

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
- M6.5.3 Dark：Stage 1 = PASS；Stage 2 Playwright **4 passed** covers 1440/1024/390, dialog/sheet, system-theme sync, Axe, overflow and console errors；Stage 1 evidence `.ai-handoff/visual/m653/dark/` 与 Stage 2 evidence `.ai-handoff/visual/m653-stage2/` 独立保留；m652 Glass evidence restored after regression capture。
- M6.5.4 Neumorphism：focused Playwright **4 passed**；Stage 1/2 evidence 位于 `.ai-handoff/visual/m654/neumorphism/`，三主题对比位于 `.ai-handoff/visual/m654/compare/`；M6 16、Dark Stage 2 4、Dark Stage 1 2、Glass 2、real integration 2；typecheck/build/Vitest 4；fresh installed-package V2 **488 passed**；compileall/Anti-AstrBot/diff-check/secret+PII/axe/overflow/console/system-theme PASS。
- M6.5.4.1 Theme UX：focused Playwright **2 passed**；System light→Glass、System dark→Dark、explicit Glass/Dark/Neu OS independence、reload persistence、backend payload mapping、Axe/overflow/console PASS；evidence 位于 `.ai-handoff/visual/m6541/`。
- M6 Final Candidate：candidate Playwright **1 passed**；M6/real integration **18 passed**；theme/material focused **14 passed**；WebUI typecheck/build/Vitest **4 passed**；1440/1024/768/390 overflow、System resolution、explicit-style OS independence、persistence、Axe Home/Settings/Agent/Dialog/More sheet、console/page errors PASS；evidence 位于 `.ai-handoff/visual/m6-final-candidate/`。

## real_environment

- M4 Real Provider Tool Call PASS；M4 Real QQ Agent E2E PASS
- M5 local real HTTP smoke PASS（无 QQ/NapCat 依赖）

## known_limitations

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh。

## POST-M7 P1A SAFETY & DATA INTEGRITY CHECKPOINT（2026-08-22）

- `M7 FINAL = PASS`；`POST-M7 P0 RELIABILITY AUDIT = PASS`；`POST-M7 P1A = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`。
- `DAILY-USE CANDIDATE = NOT_READY`；`REAL QQ / REAL PROVIDER = NOT_AUTHORIZED`；`M8 = NOT_AUTHORIZED`。
- Authorized work used disposable SQLite, synthetic data, Fake NapCat, local/fake provider, and a controlled worker. No production DB, real integration, new channel, SSE replay, durable Agent memory, schema/API/protocol redesign, or M8 work.
- Evidence: `.ai-handoff/evidence/stability/p1a/`；P1A focused **17**、fresh installed-package full V2 **530**、Web typecheck/build/Vitest **4**、Chromium **42**、compileall/Anti-AstrBot/secret-PII/diff-check PASS。
- Confirmed and fixed one restore defect: SQLite foreign-key enforcement required parent rows to be flushed before child rows. No schema change.

## 11. M7.2 ONEBOT REMINDER DELIVERY CHECKPOINT（2026-08-22）

- **[REPO_CONFIRMED]**：Starting HEAD `2acad44e865eb99b21edf7c53e6da83e66469442`；M7.1 external review = `PASS`；M7.2 external source review = `PASS`；Real QQ E2E = `NOT_RUN`。
- **[IMPLEMENTED]**：closed `noop|onebot` delivery mode（默认 Noop）、source-scoped OneBot GROUP delivery、deterministic privacy-safe reminder template、safe `Reminder.error` taxonomy、duplicate fire guard、runtime startup/shutdown ordering。
- **[CLEANUP]**：A02 真实 disconnected connection-test coverage；ActivationGuide Agent step now follows actual `/agent/threads` state；minimal reminder failure/status visibility。
- **[EVIDENCE]**：`.ai-handoff/evidence/m72/`；fake NapCat success/disconnected/action-failure traces；REAL QQ E2E = `NOT_RUN`。
- **[BOUNDARY]**：Schema/API changes = NONE；no automatic retry；no extra channel。

## 12. M7.3 BOUNDED AGENT COPILOT CHECKPOINT（2026-08-22）

- **[AUTHORIZED]**：M7.2 external review = `PASS`；M7.3 bounded Agent Copilot implementation was explicitly authorized。
- **[IMPLEMENTED]**：All mutation tools require code-enforced confirmation; pending state is in-memory, source-scoped, thread-scoped, frozen, replay-safe and restart-cleared；actual high-level tool activity uses the existing Agent API field；WebUI confirmation actions are text-compatible。
- **[SECURITY_FIX]**：External review blocker fixed：existing Agent threads are source-bound in runtime and fail closed before old history/provider use on source mismatch；same-source continuity remains intact；WebUI source changes clear local messages and conversation ID；thread summaries retain the original source binding。
- **[A10]**：Official fixture runs through real TaskPipeline/TaskService/ReminderService/AgentRuntime and synthetic reminder sink in local deterministic Step 0–16；duration/evidence at `.ai-handoff/evidence/m73/`。
- **[BOUNDARY]**：Schema changes = `NONE`；new API endpoint = `NONE`；Fake NapCat = `PASS`；Real QQ M7 E2E = `NOT_RUN`；no M7.4。
- **[CURRENT_GATE]**：External Final Review = `PASS`；`M7.3 = PASS`；`M7 FINAL = PASS`；`M7.4 = NOT NEEDED / NOT AUTHORIZED`。

## next_gate

Post-M7 P0 reliability audit is complete and awaiting External ChatGPT review. Keep `DAILY-USE CANDIDATE = NOT_READY`; do not start M7.4 or an automatic M8. Any next implementation requires a fresh product/reliability authorization。

## 13. POST-M7 P0 REAL-WORLD RELIABILITY AUDIT（2026-08-22）

- **[SCOPE]**：本轮只做代码事实检查、风险登记和测试计划；未修改 `src`、`web/src`、tests、Schema 或 API。
- **[DOCUMENTS]**：`docs/stability/RELIABILITY_MATRIX.md`、`docs/stability/RISK_REGISTER.md`、`docs/stability/STABILIZATION_PLAN.md`。
- **[FINDING]**：confirmed P0 bugs = `0`；P1 risks requiring reproduction = `8`；P2 bounded follow-ups = `5`。未将“真实 QQ 未运行”、M3 atomicity limitation、SSE no-replay 或 Agent in-memory state 误报为已发生事故。
- **[CURRENT_GATE]**：`M7 FINAL = PASS`；`POST-M7 P0 RELIABILITY AUDIT = COMPLETE_AWAITING_EXTERNAL_REVIEW`；`DAILY-USE CANDIDATE = NOT_READY`；`M8 = NOT_AUTHORIZED`。

## architecture_decisions

- ADR-001 ~ ADR-013 + M4/M5 decisions in `.ai-handoff/DECISIONS.md` / docs。

## 10. M7.1 FIRST-USE ACTIVATION CHECKPOINT（2026-08-22）

- **[REPO_CONFIRMED][CURRENT]**：Starting HEAD `7b915e0c421b0969a104df7ac9e1251a9875b33d`；M7.0 Product Contract = `PASS`；M7.1 已获授权并完成实现，等待外部审核。
- **[SOURCE_AUDIT]**：`pending_confirm` 在 TaskStatus/DB/TaskService/API/WebUI 均为 canonical；Connection Test 复用 `POST /api/v1/sources/{source_id}/test`；API/Schema changes = NONE。
- **[IMPLEMENTED]**：Home 5 分钟启动引导、Connections actionable empty/disabled/failure copy、Task/Message provenance + trust presentation、Agent 手动连接入口、真实 TaskPipeline deterministic harness、显式日期+时间解析修复。
- **[TEST_CONFIRMED]**：M7.1 backend focused 8 passed；pipeline/time regression included 85 passed；WebUI typecheck/build PASS；M7.1 Playwright 2 passed。
- **[BOUNDARY]**：A08 未扩展 confirmation framework；A09 仅 fake delivery observer；runtime 仍 NoopDelivery；无真实 QQ/NapCat；未宣称 full five-minute E2E 或 M7 complete。
- **[HISTORICAL_GATE]**：`M7.1 FIRST-USE ACTIVATION = PASS`；`M7.2 REMINDER DELIVERY = PASS`；current gate is recorded in Section 12。
