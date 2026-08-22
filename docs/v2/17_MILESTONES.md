# 17_MILESTONES.md

> M1-M7 详细定义与 PASS 标准。**代码存在不算 PASS**；必须达到明确验收。每 Milestone 完成后：真实测试 → 更新项目状态 → checkpoint → push → 外部审核 → 才进入下一个。
>
> **当前 active gate**：M5 FINAL = **PASS**；M6 FINAL = **PASS**（CampusCue WebUI completed）；M7 ROADMAP DESIGN = **PASS**；M7.0 PRODUCT CONTRACT = **PASS**；M7.1 FIRST-USE ACTIVATION = **PASS**；M7.2 ONEBOT REMINDER DELIVERY = **PASS**；M7.3 BOUNDED AGENT COPILOT = **IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；M7 FINAL = **IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW**；M7.4 = **NOT_AUTHORIZED**。

## M1：Independent QQ Runtime

**范围**：CampusRuntime / CampusEvent / EventBus / Router / OneBotAdapter / Echo Handler。

**实现**：
- `v2/src/campuscue/`（独立 implementation root，ADR-011；与 Legacy `campuscue/` 物理隔离）
- `app/runtime.py` 生命周期（07_RUNTIME_LIFECYCLE，M1 只激活 Config/EventBus/Router/OneBotAdapter/Echo）
- `core/events.py` CampusEvent（06_DOMAIN_MODEL 第一版字段：event_id/trace_id/platform/conversation_id/conversation_type/group_id/sender_id/message_id/text/segments；ID 全字符串，时间 UTC-aware）
- `core/bus.py` **有界** asyncio.Queue（`await put` 背压）+ **有界 in-flight handler 并发**（semaphore）+ 每事件 Task + 强引用 + 异常隔离 + shutdown drain
- `core/router.py` Guard（valid message / stateless self-message defense / EchoHandler 选择）+ `handlers/echo.py`
- `adapters/onebot/` **Reverse WebSocket SERVER**（NapCat 为 client 拨入；configurable host/port/path、token 校验、单 active connection + stale replacement + **generation 竞态保护**、disconnect cleanup）+ `converter.py`（纯函数，Event Frame vs Action Response Frame 分类）+ `protocol.py`（action 构建/校验）+ `dedup.py`（transport dedup）+ sender（text，echo correlation：register-before-send、timeout/pending cleanup/断连 fail-all）
- `core/outbound.py` OutgoingMessage（平台中立；业务层不构造 OneBot action JSON）
- `config.py` 最小配置（host/port/path/token env/queue/in-flight/action timeout/pending bound/dedup TTL+capacity）
- `scripts/check_no_astrbot.py`（Anti-AstrBot Gate：AST import 扫描 + 依赖扫描 + 隔离 smoke）
- 日志：NORMAL MODE 脱敏（不记录 QQ ID/群号/消息正文）；`CAMPUSCUE_DIAGNOSTIC=1` 显式诊断模式（默认 OFF，仅验收用，真实 ID 不 commit）
- 启动安全：非 loopback host 拒绝启动（除非显式 LAN opt-in + token，M1 未实现 LAN 安全）

**M1 明确不做**：DB、Task Pipeline、SourceRepository/SourcePolicy（M2 起）、Agent、Reminder、API、WebUI、at/reply/image 发送（仅解析到段）。

**验收（REAL ENV VERIFIED 才 PASS）**：
- **核心证据：真实 QQ 群发送 `hello`，真实收到 `received: hello`**（E2E 完整闭环，不依赖日志 dump）
- 辅助证据（可选，diagnostic 模式，默认关闭且不持久化）：控制台可见 `platform=onebot conversation_type=group ...`（ID 脱敏处理，不记录完整 QQ ID/群号/消息正文）
- **AstrBot 完全不运行**；代码无 `import astrbot`（Anti-AstrBot Gate 通过）
- 独立安装验证：fresh venv 安装 v2/ 后 import + 运行成功（不依赖 Legacy root / AstrBot）
- 真实 ID 在 HANDOFF 中脱敏（hash/last4）；token 永不出现

## M2：Task Pipeline（含 Provider Foundation）

> **M2a（完成，FINAL PASS）**：Data + Provider Foundation。**M2b.1（完成，FINAL PASS）**：AI-first Task Extraction Pipeline（ADR-013：本地规则不做语义 gate；LLM 单次 triage+extraction；Mock Provider + SQLite 全链路）。**M2b.2（完成，REAL_ENV PASS，2026-08-10）**：真实 Provider（DeepSeek）+ 真实 QQ/NapCat + 真实 SQLite 验收。**M2 FINAL = PASS（@ 23083cb）。**
>
> **M3（完成，FINAL PASS）**：Reminder 子系统（schema v2）——DB reminder facts（canonical）+ ReminderService（幂等 plan/cancel/resync/fire；startup resync 从 Tasks 对账）+ APScheduler 3.11 派生 jobs（确定性 job_id）+ TaskService 生命周期联动 + quiet-hours 契约。**M4（实现完成，真实环境验收完成）**：Agent tool loop 已实现；Real Provider Tool Call 与 Real QQ Agent E2E 均已通过 Workspace Agent local evidence 验收。**M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW；M4 FINAL = NOT YET DECLARED；M5 = NOT_AUTHORIZED。**

**范围**：
- **M2a Provider Foundation**（原 M4 部分，**I 修正：Provider 前移至 M2**，M4 不重新造）：
  - `BaseProvider` / `LLMRequest` / `LLMResponse` / `ProviderError` taxonomy（timeout/auth/rate_limit/network/model/malformed）
  - `OpenAICompatibleProvider`（structured output / json_schema 能力、timeout、secret_reference）
  - 最小 `ProviderManager`（配置驱动实例化 + get_default + test 连接）
  - **无 Agent、无 Tool 系统**（M4 才加）
- **M2b Task Pipeline**：
  - `SourceRepository` + `SourceService`（来源配置最小逻辑，J 修正：M2 就要，不等 M5）
  - `ExtractionRepository`（抽取审计落库）
  - `TaskRepository` / `TaskService`
  - SourcePolicy / Prefilter / ContextCollector / LLM Extraction / TimeNormalizer / Dedup
  - SQLite（sources/tasks/extractions 表，09_STORAGE）
- 详见 10_TASK_PIPELINE（L0-L7 自 M2 激活；L8 Reminder 自 M3；L9 Realtime 自 M5）

**明确不做**：Reminder（M3）、Agent/Tool（M4）、API/Realtime（M5）、WebUI（M6）、消息页。

**验收（REAL ENV VERIFIED）**：
- 真实 QQ："高数第三章作业周五晚上12点前交学习通。" → 真实 Provider → 真实 Task Pipeline → SQLite
- 验证（integration inspection / CLI / test helper / direct DB assertion，**不是 Web 页面**，K 修正）：
  - source row（来源已登记并启用）
  - extraction row（L1 分数 / L3 原始与解析 / 决议）
  - task row（title=第三章作业、category=homework、course=高等数学、deadline=本周五 23:59 +08:00、source_text_reference 保留）
  - normalized deadline 正确
  - dedup result（同消息重发 → dedup_key 命中，不重复创建）
- LLM mock 路径有测试（B13 修复）；Provider 错误分类各路径有测试

## M3：Reminder

**范围**：ReminderRepository / ReminderService / APScheduler / DB resync。

**验收**：
- 任务带 deadline → 三档提醒就位（DB reminders 行 + scheduler job）
- **重启恢复**：kill → 重启 → reminders/jobs 完整重建，无重复 job
- deadline 修改 → 旧 job 取消、新 job 就位
- complete → job 取消，到点不提醒
- delete → job 清理
- 防重复：同一 task 重复 plan 不产生重复 job
- 过期（停机期间到期）不补发

## M4：Agent（在 M2 Provider Foundation 上扩展）

**范围**（I 修正：Provider 已在 M2 完成，M4 不重新造）：
- ToolDefinition / ToolResult / ToolRegistry
- Task Tools（task_list/task_get/task_create/task_update/task_complete/task_dismiss/reminder_list/source_list）
- CampusAgentRuntime / ContextBudget / Tool Loop
- conversation/thread 最小实现

**实现**：见 08_PROVIDER_AND_AGENT。

**M4 第一版创建限制**：M2 UNIQUE `(source_id, source_message_id)` 使同一 Agent 用户消息最多创建一个 Task。第二次 `task_create` 返回安全失败结果，由 Agent 如实告知用户。M4.1 不引入 schema v3。

**验收（REAL ENV VERIFIED）**：
- 真实 QQ 提问"我这周有什么事情？" → Agent 真实 Tool Call（task_list）→ TaskService → 真实数据 → 回答（非硬编码）——**PASS（2026-08-19，Workspace Agent local evidence）**
- max_steps 防呆；重复 tool call 中止；超时/错误分类文案
- 无 Provider 配置时优雅报错（"未配置模型服务"）

## M5：API

**范围**：FastAPI（Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System）+ SSE。

**实现**：按 11_API_SPEC（M5 implemented contract）。

**状态**：**M5 FINAL = PASS**（External ChatGPT review completed before M6 authorization）。
- REST contract PASS；Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System PASS
- Backup/Restore/Import/Export PASS；SSE Realtime PASS
- Auth PASS；Runtime lifecycle PASS；Schema v3 + migration PASS
- M5.1/M5.1.1 focused tests 新增 8；full V2 **488 passed**（fresh `.venv-m511fresh` non-editable）；compileall PASS；Anti-AstrBot PASS
- SSE lifecycle、heartbeat wiring、Uvicorn readiness/occupied-port rollback、canonical health、connection.updated 均有本地证据。
- HTTP route early-close cleanup has a route-level body-iterator regression; full V2 is **488 passed** in fresh `.venv-m511fresh`。
- M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW

## M6：WebUI

**范围**：全新 WebUI（首页/任务/消息/日历/AI/接入/模型/设置），Desktop + Mobile，无 Emoji，Lucide 或统一 SVG，非开发者后台风。

**实现**：按 12_WEB_UI_SPEC + Design Tokens（M6 定具体值，配合外部视觉审核）。

**验收**：
- 自动 UI 行为测试（Playwright：桌面 + 390/599/768/1024/1440）通过，无 console error、无横向溢出
- 无障碍自动检查（焦点/alt/label）
- 生成截图 → `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL` → **外部视觉审核通过才 PASS**

**M6.1 checkpoint 实现证据**：`v2/web/` 已实现八个产品页面、真实 M5 REST/SSE 集成、任务/消息/日历/连接/模型/设置/Agent flows、Playwright full 12 passed、axe violations 0，以及 `.ai-handoff/visual/m61/` 页面级截图。M6.1 baseline 保留。

**M6.2 checkpoint 实现证据**：共享 tokens/CSS 和 presentation-level markup 完成 quiet premium polish；typecheck/build/Vitest/Playwright full 12/axe 均通过；light evidence 位于 `.ai-handoff/visual/m62/`，dark evidence 位于 `.ai-handoff/visual/m62-dark/`。M6 FINAL 尚未声明。

## M7：Full E2E

### M7.1 First-use Activation（2026-08-22）

- **状态**：`IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`；M7.0 Product Contract = `PASS`。
- **实现**：复用现有 Connections/source test、真实 L0–L7 TaskPipeline、`pending_confirm` canonical status、任务/消息 provenance、Home 轻量 5 分钟启动引导、三主题兼容的 trust summary、Agent 手动入口和 source-scoped canonical read tests。
- **官方 fixture**：`高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。`，通过 deterministic test provider + `CampusEvent` 进入真实 extraction pipeline；明确日期+时间解析为 `2026-08-28T14:00:00Z`。
- **场景**：M7-A01～A07 focused backend tests 全绿；A08 未扩展为新 confirmation framework；A09 仅 fake delivery boundary observer；A10 仅完成 Activation 证据，不宣称完整五分钟 E2E。
- **边界**：Schema/API changes = NONE；runtime 仍为 `NoopDelivery`；无真实 QQ/NapCat、无 M7.2 production reminder、无 Agent memory/planning、无 M6 UI redesign。
- **证据**：`.ai-handoff/evidence/m71/`。

**范围**：完整真实链路。

**验收（REAL ENV VERIFIED）**：
- 真实 QQ："软件杯报名星期三截止。" → 收到 → 自动判断 → 提取 Task → DB → Web 实时出现 → Reminder 建立
- 用户："最近有什么比赛？" → Agent → Tool → TaskService → 回答
- 全程无 AstrBot

## 每 Milestone 后的 Gate

真实测试 → 更新 .ai-handoff（HANDOFF/PROJECT_STATE/STATUS）→ checkpoint（secret scan + 测试）→ commit → push → 远程验证 → 外部 ChatGPT 审核 → 审核通过才进入下一 Milestone。

### M7.2 OneBot Reminder Delivery（2026-08-22）

- **状态**：`PASS`；M7.1 external source review = `PASS`；Real QQ E2E = `NOT_RUN`。
- **范围**：只实现显式 opt-in 的 OneBot GROUP reminder delivery；默认仍为 `noop`；source target 仅从 `Task.source_id` 解析。
- **实现**：确定性提醒文案、现有 `OutgoingMessage`/`OneBotAdapter.send()` 边界、safe `Reminder.error` 分类、一次性 fire claim、启动/关闭顺序收口；不改 Schema、不新增 API、不做自动重试或第二通知渠道。
- **UI**：ActivationGuide 的 Agent step 改为真实 `/agent/threads` 状态；Reminder failure/status 通过现有提醒数据在首页做最小可见反馈；A02 使用真实 connection-test disconnected path。
- **证据**：`.ai-handoff/evidence/m72/`；真实 QQ E2E = `NOT_RUN`。
- **验证**：M7.2 focused 10 passed；M7.1 + M7.2 + M3/runtime focused 55 passed；Web typecheck/build/Vitest 4；M7.1/M7.2 Playwright 3 passed。

### M7.3 Bounded Agent Copilot & Demonstration Package（2026-08-22）

- **状态**：`IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`；M7.0/M7.1/M7.2 = `PASS`；M7 Final not yet declared。
- **范围**：代码强制 Agent mutation confirmation；pending proposal 是 source/thread-scoped、in-memory、冻结参数、可拒绝、不可重放、重启清除；实际高层 tool activity 复用现有 Agent API 字段；WebUI 提供确认按钮并保留文本确认。
- **A10**：官方 fixture 通过真实 TaskPipeline、SQLite、TaskService、ReminderService、AgentRuntime 和 synthetic reminder sink 完成 local deterministic Step 0–16；不使用真实 secrets，不宣称 Real QQ。
- **交付**：`docs/demo/QUICKSTART.md`、`DEMO_SCRIPT.md`、`DEMO_TROUBLESHOOTING.md`、`v2/.env.example`、`.ai-handoff/evidence/m73/`。
- **边界**：Schema changes = `NONE`；new API endpoint = `NONE`；no durable approval framework、automatic retry、extra channel 或 M7.4。
- **验证**：External source-bound thread blocker fix completed；M7.3 focused 7 passed；relevant M4/M7.1/M7.2/M7.3 backend regression 47 passed；fresh installed-package full V2 513 passed；frontend typecheck/build/Vitest 4；full Chromium Playwright 41 passed；Fake NapCat = `PASS`；Real QQ M7 E2E = `NOT_RUN`。
