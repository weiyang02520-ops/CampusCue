# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md。

## 当前（M7 Final Closure）

- **M4 FINAL = PASS**（External ChatGPT）
- **M5 FINAL = PASS**（External ChatGPT review completed before M6 authorization）
- **M6 = CHANGES_REQUESTED → M6.1 修复完成**
- **M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**（baseline）
- **M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**（previous visual baseline）
- **M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**
- **M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**（baseline）
- **M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS**（方向与材质成立）
- **M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5.3 DARK STAGE 1 = PASS**（本地回归与基线保留）
- **M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**（Stage 2 implementation complete）
- **M6.5.4 NEUMORPHISM = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**（Stage 1/2 implementation complete）
- **NEUMORPHISM MATERIAL = PASS**（source/architecture review）
- **M6.5.4.1 THEME UX = PASS**
- **GLASS FINAL = PASS**
- **DARK FINAL = PASS**；**NEUMORPHISM FINAL = PASS**
- **M6 FINAL = PASS**（CampusCue WebUI completed）
- **M7 ROADMAP DESIGN = PASS**
- **M7.0 PRODUCT CONTRACT = PASS**
- **M7.1 FIRST-USE ACTIVATION = PASS**
- **M7.2 ONEBOT REMINDER DELIVERY = PASS**（External source review；Real QQ E2E = NOT_RUN）
- **M7.3 BOUNDED AGENT COPILOT = PASS**（External source/architecture review）
- **M7 FINAL = PASS**（External Final Review）
- **M7.4 = NOT NEEDED / NOT AUTHORIZED**
- 本 checkpoint：删除旧 Appearance section、`themeOptions`、`appearance-picker` 和隐藏兼容 CSS；保留单一 `跟随系统 / 玻璃拟态 / 深色界面 / 新拟态` 选择器，完成三主题全路由/响应式/可访问性回归，证据位于 `.ai-handoff/visual/m6-final-candidate/`。External final visual review 已通过 Glass、Dark、Neumorphism、Theme switching、persistence、backend contract、responsive、accessibility 与 regression；仅修复 Dark dialog description 的 WCAG 对比度边界，不改材质、布局、IA、业务流程、API contract、router、backend 或 schema。

### M7.0 Product Contract

- `docs/v2/M7_PRODUCT_CONTRACT.md` 已完成并通过 External ChatGPT review；M7 Final Closure 已记录。
- 已锁定官方 deterministic fixture、OneBot/NapCat source scope、Primary Reminder Delivery = QQ/OneBot outbound、Test Fallback = fake delivery sink、Agent boundary、Trust Contract、M7.1 Required/Optional/Forbidden 和 M7-A01～M7-A10。
- M7.1/M7.2/M7.3 implementation details and evidence are recorded below；final evidence is in `.ai-handoff/evidence/m73/`。

## M6.1 修复范围

- Task status 统一为后端 canonical `pending_confirm | pending | done | dismissed`；任务筛选、编辑、删除、截止时间清除、完成/驳回和双提交保护均走真实 API。
- SSE 改为带 Bearer header 的 fetch reader，消费命名事件并以 REST refresh 为 canonical；不把 token 放入 URL。
- Settings 只发送后端允许字段；System status/logs/backup/restore/import/export 已接线。
- Calendar 使用真实 deadline 查询和月导航；Messages/Connections/Providers/Agent source selector 均补齐真实查询或 CRUD/test/delete/toggle flows。
- `v2/web/tests/real_backend.py` 使用隔离 SQLite、真实 M5 composition、确定性 local fake provider upstream；不使用 QQ、真实 API key 或真实 PII。

## M6.2 视觉精修范围

- 新增 `accent/accent-soft/surface-tint/shadow-raised/shadow-overlay` tokens；统一 surface、border、button、hover、active、dialog、toast 和 mobile nav 微交互。
- Home：Today accent line、焦点日精致 active state、AI card accent-soft 层级。
- Tasks：列表 hover/focus、neutral category chip、status micro-badge、7 日/24 小时/overdue deadline tone。
- Agent：Sparkles brand mark、淡 accent empty state、composer focus ring；不再使用机器人图标。
- Calendar/Messages/Connections/Providers/Settings：复用同一套状态点、confidence bar、surface hierarchy 和 section rhythm。
- baseline `.ai-handoff/visual/m61/` 保持不变；新 light evidence 在 `.ai-handoff/visual/m62/`，dark evidence 在 `.ai-handoff/visual/m62-dark/`。

## M6.2.1 产品细节收口范围

- Home 日期、星期条、当天任务和本周 pending 计数按 Settings timezone 生成；upcoming 按 deadline 排序；完成与忽略调用分离的 API action。
- 移动端底栏收口为总览/任务/日历/AI/更多；更多使用可访问 bottom sheet，包含消息/连接/模型提供商/设置，并支持 Escape、遮罩关闭、焦点恢复和当前路由 active state。
- 前端运行时优先级只保留 `low | normal | high`；TaskRow、Calendar、Editor 使用共享中文 category/status/priority label helper；主题切换显示与图标匹配；移除 topbar 假头像。
- 不改 RealtimeHub、M5 contract、M6 IA 或进入 M7；新增独立 `.ai-handoff/visual/m621/` 与 `.ai-handoff/visual/m621-dark/`，不覆盖 m61/m62 evidence。

## M6.3 Visual Character Pass 范围

- 保留 M6.2.1 的 Blue + Teal、IA、布局、API、store、router、backend、schema 和业务逻辑；新增 Cue Line + Cue Dot 品牌母题、section tint、page identity、空状态层级和更自然的内容比例。
- Home、Tasks、Agent、Calendar 先做核心视觉收口；Messages、Connections、Providers、Settings 统一 signal、source、provider、settings 的细节节奏。
- 重点修复 Tasks/Messages/Providers/Agent 的“骨架页”观感、Calendar 的机械格子、Desktop 留白和 Mobile Agent composer 与底栏关系；不使用渐变、玻璃、neon、插画、emoji 或新增图片。
- `m6.2.1-ui-baseline` 已指向 `01461b9e4a9ece79ee0ed01343277f71ea803aef` 并推送；新证据独立写入 `.ai-handoff/visual/m63/` 与 `.ai-handoff/visual/m63-dark/`。

## 本轮验收（M5 API — PASS）

- FastAPI REST `/api/v1`：Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System + Health/Status/Logs。
- SSE `/api/v1/stream`：RealtimeHub bounded queue；notifier 注入 TaskService/ReminderService/TaskPipeline；无 replay。
- Schema v3：settings 表、sources.deleted_at 软删除、M5 索引；v1→v2→v3 atomic migration。
- Backup/Restore/Import/Export：逻辑 JSON backup、单事务 restore、V1 `campuscue.tasks` import。
- Auth：loopback 默认无认证；`CAMPUSCUE_REQUIRE_AUTH=1` / 非 loopback 强制 Bearer token。
- Runtime lifecycle：API 最后启动，shutdown 先停 API；API startup failure 进入 rollback。

## M5.1 Final Hardening（Workspace Agent local evidence）

- Finding A PASS：bounded SSE overflow marks a subscriber closed, wakes the active stream, and the generator terminates; disconnect cleanup and normal-subscriber isolation are tested.
- Finding B PASS：`ApiConfig.sse_heartbeat_interval` is passed by `/api/v1/stream`; the route wiring is tested with a short configured interval.
- Finding C PASS：runtime waits for Uvicorn `server.started` with a bounded timeout; Uvicorn startup `SystemExit` is contained in the owned task; occupied-port startup reaches `FAILED` and rolls back API, adapter, bus, and DB.
- Finding D PASS：only `/api/v1/health` is registered; `/api/v1/system/health` is absent from OpenAPI.
- Realtime completeness PASS：task, reminder, extraction and adapter connection producers are present; `connection.updated` crosses the neutral Adapter callback boundary and is tested through the real connection lifecycle.
- Commit ordering PASS：business mutations commit before notification; TaskService, ReminderService and TaskPipeline isolate notifier failures so derived realtime cannot turn a successful mutation into an API failure.

## M5.1.1 Final SSE Route Cleanup

- The `/api/v1/stream` outer generator now unsubscribes in `finally`, covering an HTTP consumer that closes immediately after `: connected` before `RealtimeHub.stream()` enters its own lifecycle.
- Route-level ASGI body-iterator regression confirms early close leaves `subscriber_count() == 0`.

## M6.5.2 Glass Refinement & Productization

- **External review result**：M6.5.1 Glass direction = PASS；Atmospheric Backdrop、Tint、Blur、Edge Light、Shadow 和 Contrast 已达到可感知的 Glassmorphism。M6.5.2 收口 backdrop 过强、材质 tier 不统一、工具控件过实、Home 嵌套白卡、Tasks raw ISO 和移动端层级。
- **实现**：新增 semantic Glass tiers（Base / Primary / Context / Raised / Floating）与统一 blur/elevation tokens；降低 light backdrop（尤其 warm amber）；Home Today 直接承载 empty content；Tasks toolbar/context/rows 统一层级；Agent context、head utilities、prompt chips、composer 收口；移动端 Agent separation 与 bottom nav 保持玻璃层级；Settings backup preview 使用共享本地化日期 formatter。
- **范围**：Stage 1 仅 App Shell、Home、Tasks、Agent；不扩张 Dark/Neumorphism，不改 IA、dataset、API、store、router、backend、schema、M5 或 M4。
- **证据**：新增 `.ai-handoff/visual/m652/glass/` 五张 Stage 1 refinement screenshots；M6.5.1 `.ai-handoff/visual/m651/glass/` 从 `m6.5.1-glass-baseline` 恢复，未覆盖。
- **验证**：M6.5.2 focused Glass 2 passed；M6 focused Playwright 16 passed；M6.5.1 regression 1 passed；real integration 2 passed；typecheck/build/Vitest 4 passed；fresh installed-package full V2 488 passed；compileall/Anti-AstrBot/diff-check/Secret+PII scan PASS；axe 0、responsive overflow、console error、theme persistence、fallback PASS。

## M6.5.3 Dark UI Stage 1

- **基线**：创建并推送 annotated tag `m6.5.2-glass-baseline`，指向本轮起始 Glass commit `63d7aeb4177b61bc73bffa336d6743e50c780559`；M6.5.2 Glass evidence 保持未覆盖。
- **实现**：新增独立 Dark solid-surface visual language；深色 canvas/elevated canvas、neutral/raised/floating surfaces、blue context、teal context、control borders、contrast-first text and focus tokens；不使用大面积 backdrop blur、透明玻璃、atmospheric cyan gradient 或白色 edge highlight。
- **范围**：Stage 1 仅 App Shell、Home、Tasks、Agent、Settings Theme Selector；IA、layout、font、spacing、grid、responsive、API、store、router、backend、schema、business logic 保持不变；Stage 2 暂缓。
- **证据**：新增 `.ai-handoff/visual/m653/dark/` 七张 Stage 1 screenshots。
- **验证**：Dark focused Playwright 2 passed（Axe 0、responsive overflow 0、console/page error 0、theme persistence、Glass fallback、mobile composer safety）；M6 focused 16 passed；M6.5.2 Glass focused 2 passed；real integration 2 passed；typecheck/build/Vitest PASS。
- **Gate**：**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**DARK FINAL = NOT YET DECLARED**；**NEUMORPHISM = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M6.5.3 Dark UI Stage 2

- **实现**：Calendar、Messages、Connections、Providers、Settings、Dialog、Bottom Sheet、Toast、Empty/Loading/Offline/Reconnecting 的 Dark solid-surface 收口；补齐 1440/1024/390 evidence 与 Glass/Dark comparison。
- **主题**：Theme Selector 使用真实 `跟随系统 / 玻璃拟态 / 深色界面` 标签；后端值保持 `system/light/dark`；`system` 由 `prefers-color-scheme` 解析、监听并持久化。
- **证据**：`.ai-handoff/visual/m653-stage2/dark/`、`.ai-handoff/visual/m653-stage2/compare/`；不覆盖 Stage 1 或 Glass evidence。
- **验证**：Stage 2 Playwright **4 passed**；Stage 1 Dark **2 passed**；M6 **16 passed**；Glass **2 passed**；real M5 integration **2 passed**；typecheck/build/Vitest **4 passed**；fresh installed-package V2 **488 passed**；compileall/Anti-AstrBot/diff-check/secret+PII/axe/overflow/console/system-theme PASS。
- **Gate**：Stage 1 = **PASS**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**DARK FINAL = NOT YET DECLARED**；**NEUMORPHISM = NOT_AUTHORIZED**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## Verification（Workspace Agent local evidence）

- Full V2 pytest：**488 passed**（fresh installed-package `.venv-m511fresh` non-editable）
- M5/M5.1/M5.1.1 focused：**24 passed**；M5.1.1 new test：**1 passed**
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS
- uvicorn local HTTP smoke PASS（health/task CRUD/reminders/backup）
- Local readiness/SSE smoke PASS；occupied-port startup failure and rollback PASS。
- These are local Workspace Agent results, not independent External ChatGPT execution。
- WebUI `pnpm typecheck` PASS；`pnpm build` PASS；Vitest 2 passed；Playwright full **12 passed**；axe violations 0；截图覆盖 1440 全页面、390 home/tasks/editor/calendar/agent/settings、1024 tasks、768 calendar，见 `.ai-handoff/visual/m62/`；dark evidence 见 `.ai-handoff/visual/m62-dark/`。
- Real integration PASS：真实 API task mutation → named SSE → REST refresh；task CRUD/deadline clear/done；calendar navigation；source test；local fake provider test；settings save；export download。
- M6.2.1 focused：typecheck PASS；Vitest 4 passed；Playwright focused 12 passed；axe violations 0；light/dark m621 screenshot capture PASS；视觉抽查通过。
- M6.3：typecheck/build PASS；Vitest 4 passed；focused Playwright 12 passed；axe 0；real integration tests individually PASS；light/dark m63 screenshot capture PASS；mobile Agent composer verified above bottom nav。

## Known limitation / open design risk

- M4 first-version `(source_id, source_message_id)` uniqueness remains；M5 schema v3 does not change it。
- M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- SSE no-replay；断线后 REST refresh canonical state。

## Next gate

External Final Review completed: M7.3 and the M7 Final Gate are PASS. Do not open M7.4 or automatically start M8。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- Acceptance used isolated temp DBs; fresh venv and runtime data are not committed。

## M6.4 Information Layering Pass

- Baseline tag `m6.3-ui-baseline` points to `5152bc6b5008e8c6fdf2cf28ff8040d87e416699`; prior M6 evidence is preserved。
- Tasks now prioritize title/deadline/status, with a collapsible context aside, sheet filters, explicit complete action, and low-frequency edit/dismiss/delete in More。
- Agent now has a desktop conversation/context split, collapsible context rail, four prompts, mobile context sheet, and real deterministic Agent API conversation evidence。
- Messages now default to the latest record in a desktop master/detail workspace, with mobile detail sheet and advanced metadata collapsed。
- Calendar selected-day agenda and capped task dots; Connections summary/advanced details; Providers safe credential summary; Settings collapsed recent logs。
- No backend/API/store/router/schema/SSE/business logic changes; user-facing engineering copy was removed。Visual fixture dataset is 5 tasks / 3 messages / 3 sources / 1 provider。

## M6.4 Verification（Workspace Agent local evidence）

- Fresh installed-package `.venv-m64fresh` full V2 pytest: **488 passed**。
- WebUI typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**。
- Light evidence `.ai-handoff/visual/m64/`; dark evidence `.ai-handoff/visual/m64-dark/`。
- compileall PASS；Anti-AstrBot PASS；git diff --check PASS；secret/PII scan PASS。
- **M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M6.5 Visual Depth & Product Composition

- Baseline tag `m6.4-ui-baseline` points to `26392e633b1ab47bfe39c1831c774c638f9b7076`; prior m63/m64 evidence is preserved。
- Page composition now uses differentiated max-widths, editorial grids, canvas/section/primary/raised surface hierarchy, stronger typography scale, and a restrained Blue + Teal cue system。
- Glassmorphism is local only: Agent canvas/context/composer, Home focus surfaces, connection indicator, inspector/diagnostics and dialogs; long task/message rows and settings form remain readable solid/tinted surfaces。
- `backdrop-filter` has a solid fallback via `@supports not`; no new data, API, store, router, backend, schema or business logic。
- New evidence is under `.ai-handoff/visual/m65/` and `.ai-handoff/visual/m65-dark/`。

## M6.5 Verification（Workspace Agent local evidence）

- WebUI typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**。
- Light/dark screenshot capture PASS；responsive evidence covers 390/768/1024/1440；visual dataset remains 5 tasks / 3 messages / 3 sources / 1 provider。
- **M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M6.5.1 REAL Glassmorphism Correction

- Starting HEAD: `524e4a13a2ba257fa5b04194219c17c9d6cd068c`（M6.5 visual-depth implementation）；不 amend 旧提交。
- 只返工 Glass 核心四处：App Shell、Home、Tasks、Agent；Calendar/Messages/Connections/Providers/Settings 的 Glass 扩张暂缓。
- 建立连续 CampusCue Atmospheric Canvas（Blue/Cyan/Teal/Muted Indigo with minimal warm light），并拆分 `glass-subtle/panel/raised/floating` 材质层。
- Glass anatomy 已明确落地：Backdrop、半透明 Tint、分级 Blur、top/left Edge Light、前后层级 Shadow、Text Contrast First、solid/tinted fallback。
- Task rows、message bubbles、calendar cells 不做逐项 blur；内容层保持稳定可读，Glass 集中在 Shell、Primary Workspace、Context、Toolbar、Composer 和 Floating UI。
- 专用 Playwright evidence/test：`.ai-handoff/visual/m651/glass/`，含 `glass-shell/home/tasks/agent` 1440、Home/Agent 390 与 test-only atmosphere marker 截图。

## M6.5.1 Verification（Workspace Agent local evidence）

- typecheck/build PASS；M6 focused Playwright **16 passed**；Glass material Playwright **1 passed**；axe 0（focused suite）；responsive 390/599/768/1024/1440 PASS。
- Glass evidence 已通过内部视觉检查：Shell atmosphere 连续、Agent marker 可透过 tint + blur 感知、Glass container / opaque content / raised composer 层级可分辨。
- **M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS**（historical direction gate）；**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**GLASS FINAL = NOT YET DECLARED**；**DARK REVIEW = PENDING**；**NEUMORPHISM REVIEW = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## M7.1 First-use Activation（current）

- Starting baseline `7b915e0c421b0969a104df7ac9e1251a9875b33d`；M7.0 Product Contract = `PASS`。
- Implemented only the approved M7.1 slice: source activation guidance, existing connection test reuse, deterministic local pipeline harness, provenance/trust presentation, manual grounded-Agent entry, and named M7-A01～A07/fake reminder tests.
- `pending_confirm` canonical support = YES；Connection-test canonical support = YES；API changes = NONE；Schema changes = NONE。
- Explicit date+clock normalization now preserves the official fixture deadline as `2026-08-28T14:00:00Z` while preserving bare-date behavior.
- M7.1 evidence: `.ai-handoff/evidence/m71/`；external source review = `PASS`。
- **HISTORICAL GATE**：`M7.1 FIRST-USE ACTIVATION = PASS`；`M7.2 ONEBOT REMINDER DELIVERY = PASS`；M7.3 is tracked in the current section below。Do not declare M7 FINAL from local evidence alone。

## M7.2 OneBot Reminder Delivery（current）

- Delivery mode is closed `noop|onebot`; default external delivery is OFF。
- Only enabled, non-deleted OneBot GROUP sources are eligible, resolved strictly through `Task.source_id`。
- Existing `OutgoingMessage` and `OneBotAdapter.send()` are reused; no protocol JSON is built in ReminderService。
- Reminder failure categories are safe `delivery:*` values in the existing `Reminder.error` field；no automatic retry。
- Runtime installs delivery before scheduler start and stops scheduler before adapter；duplicate fire produces zero duplicate outbound actions。
- Evidence: `.ai-handoff/evidence/m72/`；fake NapCat PASS；REAL QQ E2E = `NOT_RUN`。
- Schema/API changes = `NONE`；M7.3 implementation mapping is recorded in the closed section below。

## M7.3 Bounded Agent Copilot（closed）

- All Agent mutations are code-enforced confirmation writes: `task_create`, `task_update`, `task_complete`, `task_dismiss` are metadata-classified in `ToolRegistry` and never execute on the proposal turn。
- Pending arguments are frozen, in-memory, source-scoped and thread-scoped；reject/ambiguous/replay/cross-source/restart cases are covered. Confirmation executes the frozen proposal directly through `ToolRegistry` and `TaskService`。
- Existing `/api/v1/agent/chat` now returns actual high-level `tool_activity` and `confirmation_state`; no `/agent/confirm`, schema migration, or durable approval storage was added。
- WebUI displays safe activity and explicit `确认`/`取消` actions；scheduled reminder copy is truthful under default Noop delivery。
- External blocker fix：runtime now fails closed before old Conversation history/provider use when a thread is presented under another source；same-source continuity remains intact，`thread_summary` retains the original binding；WebUI source switching clears messages and conversation ID。
- M7-A10 local deterministic Step 0–16 uses the official fixture and real pipeline/service/runtime chain; evidence and screenshots are in `.ai-handoff/evidence/m73/`。
- Focused M7.3 backend 7, relevant M4/M7.1/M7.2/M7.3 backend regression 47, fresh installed-package full V2 513, frontend typecheck/build/Vitest 4, and full Chromium Playwright 41 passed. Real QQ M7 E2E remains `NOT_RUN`。
- **Current gate**: `M7.3 = PASS`; `M7 FINAL = PASS`; `M7.4 = NOT NEEDED / NOT AUTHORIZED`。

## POST-M7 P0 REAL-WORLD RELIABILITY AUDIT（2026-08-22）

- M7 Final remains **PASS**. This is a separate stabilization gate, not M8 authorization。
- **POST-M7 P0 RELIABILITY AUDIT = COMPLETE_AWAITING_EXTERNAL_REVIEW**；**DAILY-USE CANDIDATE = NOT_READY**；**M8 = NOT_AUTHORIZED**。
- Audit documents: `docs/stability/RELIABILITY_MATRIX.md`、`docs/stability/RISK_REGISTER.md`、`docs/stability/STABILIZATION_PLAN.md`。
- Reviewed OneBot lifecycle/reconnect/dedup/action correlation, EventBus bounds/shutdown, TaskPipeline/provider errors, Task/Reminder recovery, source-scoped delivery, Agent confirmation/isolation, SSE reconnect contract, backup/restore, and runtime lifecycle。
- Result: no confirmed P0 data-loss/secret-leak/wrong-send defect；8 P1 risks and 5 P2 follow-ups remain needs-reproduction or bounded-proof items。Real QQ E2E and Real Provider smoke remain `NOT_RUN` by design in this audit。
- No source/schema/API/test changes；no full V2/Chromium rerun。Do not fix P1/P2 items without a new narrow authorization; stop immediately for a reproduced P0。
