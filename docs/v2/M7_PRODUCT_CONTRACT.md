# CampusCue M7.0 Product Contract

> 状态：**M7.0 PRODUCT CONTRACT = PASS；M7.1 PASS；M7.2 PASS；M7.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M7 FINAL = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW**
>
> 本文把 M7 Roadmap 收敛为可测试的产品契约。它不是代码实现授权。
>
> `M7 ROADMAP DESIGN = PASS`；`M7.0 = PASS`；`M7.1 = PASS`；`M7.2 = PASS`；`M7.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`。

## 1. Product Promise

一个第一次使用 CampusCue 的学生，在 5 分钟内连接一个受支持来源，看到一条有来源证据的任务，完成必要确认，看到提醒跟进状态，并向受来源边界约束的 Agent 提问并得到基于 canonical data 的回答。

这句话中的每个结果都必须能通过 UI、API、事件、数据库事实或测试日志观察；“感觉智能”不算验收证据。

## 2. Contract Scope

### 2.1 Supported source scope

M7 MVP 只有两条 source path：

1. **Deterministic local/test source**：复用现有隔离测试 harness / synthetic source row / injected event path；不新增 connector。
2. **One real supported source**：现有 OneBot/NapCat reverse WebSocket source，使用已经存在的 `platform + conversation_id` source contract。

M7 不新增 LMS、教务系统、日历平台或第二套校园 connector。OneBot/NapCat 是本阶段唯一真实来源路径；本契约不把真实 QQ/NapCat 操作授权给当前 M7.0。

### 2.2 Canonical facts

- Task 状态、字段和 provenance 以 DB 的 `tasks` / `extractions` / `sources` / `reminders` 为准。
- SSE 只做通知；客户端断线后仍通过 REST refresh canonical state。
- Task 创建和变更仍必须经过 TaskService。
- Agent 只能访问当前 selected source scope 内的工具结果。

## 3. Five-minute Journey

下面是官方 Demo / Acceptance 的 Step 0～Step 16。实现可以改变页面细节，但不能删掉可观察结果。

| Step | User action | System action | Observable evidence | Failure state | Acceptance condition |
|---|---|---|---|---|---|
| 0 | 进入 CampusCue | 加载运行状态、来源和任务摘要 | 页面显示服务状态和当前来源状态 | 服务未连接或 API 不可用 | 用户能看到下一步，而不是空白页 |
| 1 | 打开 Connections | 加载现有 sources | 来源身份、enabled 状态、测试入口可见 | 没有来源 | 显示“添加/启用一个支持来源” |
| 2 | 配置或选择一个支持来源 | 校验 `platform + conversation_id`，不写 secret value | 来源名称/平台/会话范围可见 | 字段缺失、重复或格式错误 | 错误可解释且不创建半成品来源 |
| 3 | 执行 Connection test | 通过现有 adapter/service boundary 检查连通性 | test success、adapter 状态或明确错误 | 无活动连接、超时、未启用 | 成功时用户知道该来源可用 |
| 4 | 输入或收到 deterministic test message | local path 注入固定事件；real path 接收 OneBot message | message/extraction 记录可追踪 | 消息未进入、来源未启用 | 事件有 source identity 和 message identity |
| 5 | 等待 AI-first extraction | L0-L7 pipeline 执行 prefilter、context、LLM extraction、时间标准化、dedup、confidence | extraction status、reason、provider/model audit | prefilter drop、provider error、parse error | 不静默失败，用户能区分“无任务”和“处理失败” |
| 6 | 查看消息/任务结果 | 将 extraction 投影为候选任务或 rejected record | source、message ID/reference、confidence、字段结果 | 缺 provenance 或字段无法解释 | 用户能回答“这条任务从哪里来” |
| 7 | 对需要确认的结果做确认 | 用户确认/修正后通过 TaskService 进入 canonical task 流程 | status 从 `pending_confirm` 变为可执行任务状态 | 用户拒绝、信息不足、重复 | 任何不确定事实都不会伪装成 certainty |
| 8 | 查看任务 | 从 tasks 表加载 canonical task | title、category、course、deadline、priority、status、source provenance | duplicate 或 rejected | canonical task 与 extraction 对得上 |
| 9 | 查看提醒跟进 | 从 reminders 表读取事实，展示 scheduled/fired/cancelled 状态 | reminder trigger、task ID、状态和时间可见 | 无 deadline、任务已完成、delivery 失败 | 至少能看到提醒是否已计划/触发/取消 |
| 10 | 进入 Agent | 选择当前支持来源 | selected source、source status、scope 提示可见 | 未选来源或来源未启用 | Agent 不允许无 scope 工作 |
| 11 | 提问任务相关问题 | Agent 接收当前 source-scoped input | request/thread identity 和 selected source 可审计 | provider timeout、tool error、无任务 | 错误有可理解回复，不泄漏堆栈 |
| 12 | Agent 判断是否需要工具 | 对 canonical data 查询必须生成 bounded tool call | tool name、参数校验和 tool result 可记录 | 非法参数、重复调用、达到上限 | Agent 不凭空生成 task facts |
| 13 | Agent 返回回答 | 基于已返回 tool result 生成 grounded answer | answer 与 task/reminder 数据一致，可指出来源范围 | 无结果或数据冲突 | 回答明确时间、状态和 scope，不越权 |
| 14 | 用户修改/完成任务 | 通过 UI 或 Agent confirmation 触发 TaskService | task mutation、reminder replan/cancel、realtime event | 歧义、状态不允许、任务不存在 | 写操作可追踪且不会绕过 TaskService |
| 15 | 回到任务/提醒 | REST reload canonical state | 新状态、提醒变化、source provenance 保留 | SSE 丢事件 | refresh 后事实仍正确 |
| 16 | 完成首用闭环 | 用户知道下一步行动 | demo evidence 包含 journey start/end | 任一步只能靠人工解释 | clean run 在五分钟内完成 |

### 3.1 Five-minute timing contract

- 计时从 Step 0 首屏可用开始，到 Step 16 用户得到 grounded answer 并看到 task/reminder 状态结束。
- 允许使用 deterministic local/test source 加速测试；真实 source path 必须保留相同的可观察契约。
- 任何必须手工修改数据库、读取日志才能继续的步骤都不算成功。

## 4. Official Demo Fixture

M7 所有 acceptance 优先复用一个安全、虚构、确定性的 fixture message：

> **高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。**

### Expected extraction contract

| Field | Expected value / rule |
|---|---|
| title | `高等数学第三章作业`（允许稳定的等价短标题，但不能丢失章节与作业语义） |
| category | `homework` |
| course | `高等数学` |
| deadline | `2026-08-28T14:00:00Z`，即 Asia/Shanghai `2026-08-28 22:00` |
| confidence | 高于当前 extraction threshold，或若 fixture harness 固定为低置信度则必须进入 `pending_confirm` 并可确认；不可随机变化 |
| source provenance | 固定 synthetic source + 固定 message ID；real path 只替换 source identity，不替换字段契约 |
| submission method | 不作为 M7 必验 Task 字段；fixture 不依赖未落库的额外字段 |

Fixture 禁止真实姓名、QQ 号、群号、API key、私有 URL 和真实个人课程数据。时间使用显式年份，避免相对日期受当前时钟影响。

## 5. Reminder Delivery Decision

### 5.1 Current code facts

只读检查确认：

- `ReminderService` 持久化 reminder facts，并由 scheduler jobs 派生运行状态。
- `ReminderService.fire()` 会重查最新 task 状态，标记 reminder fired，发布 `reminder.fired`，再调用注入的 delivery boundary。
- 默认 delivery 是 `NoopDelivery`；当前 runtime 在 `v2/src/campuscue/app/runtime.py` 明确注入 `NoopDelivery()`。
- `ReminderService.set_delivery()` 已存在，delivery 是平台中立注入点。
- `OneBotAdapter.send(OutgoingMessage)` 已支持 group/private outbound action，并已有 echo correlation、timeout、connection failure 和 fake-NapCat 测试基础。
- `reminder.fired` SSE 是通知，不是 durable replay；WebUI 当前有 reminders API 数据，但 M7.0 不假设已有完整 in-app notification center。

### 5.2 Candidates

| Candidate | Product value | Complexity | Account risk | Testability | True end-to-end delivery | API/Schema impact |
|---|---|---:|---:|---:|---|---|
| A. QQ / OneBot outbound reminder | 最高：提醒回到任务来源所在会话，符合 CampusCue 的现有入口 | 中 | 中：群消息可能打扰用户，必须有 opt-in / quiet-hours / source scope | 高：已有 adapter action 与 fake NapCat path | 是，若 adapter action 成功并被 fake/real receiver 观察 | 目标是无需 Schema；可能需要 delivery wiring/config contract，是否需 API 由后续实现审查决定 |
| B. WebUI/in-app visible reminder | 中高：不接触外部账号，适合 demo 和本地使用 | 中 | 低 | 中高：可用 SSE + REST facts，但离开页面时需要 durable UX 设计 | 仅在用户可观察到页面/持久状态时是；当前 `NoopDelivery` 本身不构成 delivery | 目标是无需 Schema；可能需要现有 reminders surface / event handling，需避免伪造 fired event |
| C. Other current-native path: redacted local delivery sink / console evidence | 低：便于开发验证 | 低 | 低 | 高 | 否，不能作为产品交付 | 无，但只能做 test evidence |

### 5.3 M7 PRIMARY REMINDER DELIVERY PATH

**Primary：A. QQ / OneBot outbound reminder，限定为当前已支持的 OneBot/NapCat source。**

理由：

1. 它沿用 CampusCue 已有的真实入口和 `OutgoingMessage → Adapter` 边界；
2. 它能证明“计划提醒 → 触发 → 用户所在来源会话收到消息”的真正 end-to-end delivery；
3. fake NapCat 已有 action/echo 测试基础，不需要引入新的通知平台；
4. 它不会把 M7 变成多渠道通知平台，前提是只支持 source-scoped OneBot delivery。

M7 实现必须额外明确 delivery opt-in、目标 source resolution、重复触发保护、失败可见性、quiet-hours 和消息模板；这些是后续 M7.2 实现的验收输入，不是本轮代码授权。

### 5.4 TEST FALLBACK

**Test fallback：C. Injected fake delivery sink / fake NapCat observer。**

它只用于 deterministic local acceptance，不能被报告为用户通知产品。B 不作为第二个并行产品渠道进入 M7；若未来选择 WebUI delivery，必须先重新开一个明确的范围决策。

## 6. Agent Contract

### 6.1 KNOWS

- selected source 及其 enabled/connection status；
- 当前 source scope 内的 canonical tasks；
- task deadline/status/category/course/priority/confidence/provenance；
- 当前 source scope 内的 reminder facts；
- configured timezone；
- tool 已返回的事实和错误。

### 6.2 DOES NOT KNOW

- 其他未选来源；
- 整个 QQ 历史或未保存的群聊全文；
- 任意校园数据、Web 内容或未接入的 LMS/教务系统；
- secret value、provider credential、QQ 登录态；
- 长期个人 Memory；
- 未返回的 tool result；
- 模型自己猜测出的 task 或 reminder 状态。

### 6.3 Tool-call rules

Agent 必须调用 tool：

- 查询 canonical task；
- 查询 reminder；
- 创建、修改、完成或 dismiss task；
- 查询当前 source 或 source status；
- 任何回答需要事实数据而非一般说明时。

Agent 可以直接回答：

- 能力说明；
- 缺少字段的澄清问题；
- 对已经得到的 tool result 做简短总结；
- 明确说明“当前来源没有找到任务”。

必须请求确认：

- 有歧义的 mutation；
- deadline 改动；
- status 改动；
- 可能让用户意外的写操作；
- 模型无法可靠解析日期或目标任务时。

继续维持 bounded tool loop、source-scoped context、TaskService mutation gate 和现有 step limit。

### 6.4 Explicitly excluded

M7.0 不引入 SubAgent、MCP、Skills、Computer Use、Long-term Memory、通用 Planning framework、后台自主计划或跨来源 Agent。

## 7. Trust Contract

### 7.1 Why a user should trust a task

每条 candidate/canonical task 至少能追溯：

1. 哪个 source；
2. 哪条 source message / message identity；
3. extraction 是否成功、模型/provider audit 和 reason；
4. confidence；
5. title/category/course/deadline 等字段；
6. 哪些字段需要用户确认；
7. task 当前 status 和 reminder 状态。

### 7.2 Existing fields are sufficient for M7.0

当前 `tasks`、`extractions`、`sources`、`reminders` 与消息投影已有 `source_id`、`source_message_id`、`source_text_reference`、`confidence`、`status`、`reason`、`normalized_result`、task fields 和 reminder status，足以表达 M7 MVP 的 trust contract。

因此本轮：**没有 SCHEMA CHANGE CANDIDATE。**

如果后续验收证明 delivery attempt、user confirmation actor 或 field-level provenance 无法用现有事实表达，必须先单独记录 `SCHEMA CHANGE CANDIDATE`，经过外部审核后才可实现；不得顺手迁移。

### 7.3 Three trust states

| State | Meaning | User treatment | Canonical expression |
|---|---|---|---|
| Certain | extraction success，字段足够，confidence 达到当前 threshold，且没有未解决歧义 | 可直接进入任务流；仍展示 provenance | extraction success + task `pending` + confidence/provenance |
| Needs review | confidence 低、deadline 不完整/歧义或模型明确要求确认 | 必须确认/修正，不得伪装确定 | task `pending_confirm` + extraction reason/normalized result |
| Invalid / rejected | prefilter drop、provider/parse error、无任务或重复且不创建新 task | 不创建 canonical task；保留可解释 extraction outcome | extraction status/reason/had_task/duplicate outcome |

## 8. Technical-debt Decisions

### M3 Task/Reminder atomicity

默认保持 startup `resync_all()`。只有 M7 primary OneBot delivery path 稳定复现用户可见的 task/reminder 不一致，才授权专项修复；本轮不重做 Unit of Work 或 Reminder architecture。

### M4 source-message uniqueness

M7 不解决 compound announcement → multiple tasks。一个 source message 当前最多创建一个 Task 是本阶段产品边界；需要拆分时必须先定义新的 extraction/dedup/product semantics。

### SSE no replay

保持 notification-only + reconnect REST refresh。M7 不实现 event replay；Reminder 的事实展示必须能从 REST canonical state 恢复。

## 9. M7.1 First-use Activation Slice

### Required

- guided source connection；
- connection validation；
- deterministic local fixture；
- OneBot/NapCat real source identity contract 的 source-scoped 验证；
- provenance/confidence/trust-state presentation；
- first canonical task；
- first grounded Agent read question；
- fake delivery observer 能证明 Reminder primary path 的接口输入/输出，但不把 M7.1 变成大规模 Reminder 实现。

### Optional

- existing UI 中最小的 guided copy 或 step indicator；
- one deterministic failure replay；
- delivery status 的只读摘要；
- demo reset command/documentation。

### Forbidden

- M7.2 Reminder Delivery 的完整生产实现；
- 多平台 connector；
- Schema/API redesign；
- Agent memory/planning/SubAgent；
- Collaboration；
- M6 UI visual iteration；
- 真实 QQ/NapCat 操作作为本轮开发步骤。

## 10. Acceptance Scenarios

所有 M7.1～M7.3 实现都必须映射到下列 scenario ID；没有 scenario 映射的需求不进入 M7。

| ID | Precondition | Action | Expected result | Evidence | Failure interpretation |
|---|---|---|---|---|---|
| M7-A01 First source connection | clean local install；无 active source | 选择一个支持 source 并保存 | source identity 建立且 scope 明确 | source row/API response/UI state | 不能保存或 scope 不明确 = activation blocker |
| M7-A02 Connection failure | source 存在但 adapter 未连接/配置错误 | 执行 connection test | 明确失败原因和下一步，不创建假成功 | test response、status、redacted log | timeout/认证/连接错误未分类 = reliability failure |
| M7-A03 Message → task extraction | deterministic fixture source active | 注入固定 message | extraction 完成并产生预期 task candidate/canonical task | extraction row、task row、UI/API | 字段漂移、随机 deadline 或无 reason = extraction failure |
| M7-A04 Uncertain extraction review | fixture variant 缺 deadline/低 confidence | 查看并确认/拒绝 | 状态为 `pending_confirm`，确认后才进入可执行 task | status transition、audit reason | 不确定结果直接变 pending = trust failure |
| M7-A05 Provenance visibility | task/extraction exists | 打开消息/任务详情 | source、message identity/reference、confidence、reason 可追溯 | UI/API/database fact | 只能看见标题不能解释来源 = trust failure |
| M7-A06 Agent grounded read | selected source has canonical fixture task | Agent 问“这周我有哪些任务/高数作业什么时候截止？” | Agent tool call 查询 canonical task，并返回一致答案 | tool name/result、answer、source scope | 无 tool result 仍给事实 = hallucination failure |
| M7-A07 Agent source isolation | Source A/B have different tasks | 在 A scope 询问 B task | Agent 不返回 B facts，给出无结果/当前 scope 说明 | source IDs、tool result、answer | 跨 source 泄漏 = security blocker |
| M7-A08 Ambiguous mutation confirmation | task exists，deadline/status mutation ambiguous | 要求 Agent 修改任务 | Agent 先澄清/确认，不直接写；确认后走 TaskService | request、confirmation、task event | 直接 mutation 或绕过 TaskService = contract failure |
| M7-A09 Reminder follow-through | pending task has scheduled reminder；OneBot target source active | 触发 due reminder | reminder fact fired，primary delivery sends one scoped message，失败可见 | reminder row/event、adapter action/fake observer | 只标 fired 但用户收不到 = delivery failure |
| M7-A10 Five-minute end-to-end demo | clean fixture/reset；documented environment | 执行 Step 0～16 | 5 分钟内完成 source→task→trust→reminder status→Agent grounded answer | timestamped demo log/screenshots/API trace | 需人工改 DB、猜测或跳过步骤 = demo fail |

## 11. Gate

- `M7 ROADMAP DESIGN = PASS`
- `M7.0 PRODUCT CONTRACT = PASS`
- `M7.1 FIRST-USE ACTIVATION = PASS`
- `M7.2 ONEBOT REMINDER DELIVERY = PASS`
- `M7.3 BOUNDED AGENT COPILOT = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`
- `M7 FINAL = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW`

## 12. M7.1 implementation mapping

- `pending_confirm` canonical support: **YES** — present in `TaskStatus`, DB check constraint, TaskService, API schema and WebUI labels; reused without schema change.
- Connection-test canonical support: **YES** — existing `POST /api/v1/sources/{source_id}/test` reports adapter status; reused without a new endpoint.
- Official fixture path: test-only deterministic provider + `CampusEvent` through the real `TaskPipeline` and SQLite; no production fixture branch or second connector.
- Official fixture deadline parsing now preserves explicit date+clock (`2026年8月28日22:00前`) as `2026-08-28T14:00:00Z`; bare-date behavior remains unchanged.
- Trust presentation: Home activation guide, task provenance summary, message detail evidence/reason, and source-scoped Agent entry copy.
- Connection failure presentation: source-scoped test result, disabled-source guidance, and safe retry/status copy; no secret or traceback exposure.
- Agent boundary: M7-A06/A07 tests prove canonical task tool invocation and zero cross-source leakage. M7-A08 is not expanded beyond the existing mutation boundary.
- Reminder boundary: fake delivery observer test only; runtime remains `NoopDelivery`, and production QQ/OneBot reminder delivery remains M7.2.
- API changes: **NONE**. Schema changes: **NONE**.
- M7.1 evidence directory: `.ai-handoff/evidence/m71/`.

## 13. M7.2 implementation mapping

- M7.1 external source review: **PASS**. Cleanup includes real disconnected-path connection-test coverage and Agent activation progress derived from `/agent/threads`, not local completion flags。
- Delivery mode: closed `noop|onebot`; default `noop` keeps external delivery OFF. `onebot` requires explicit operator opt-in with reminders enabled。
- Target contract: `Task.source_id → Source` and only non-deleted, enabled `platform=onebot` GROUP sources with a numeric `conversation_id` are deliverable。
- Delivery boundary: deterministic privacy-safe text is wrapped in existing `OutgoingMessage` and sent through `OneBotAdapter.send()`; no OneBot JSON is built in ReminderService。
- Failure contract: the existing `Reminder.error` field stores only safe `delivery:*` categories; no automatic retry and no additional delivery channel。
- Duplicate contract: service-level fire claim guard prevents sequential/concurrent duplicate outbound actions without a schema change。
- Runtime lifecycle: delivery is installed after adapter start and before scheduler start; shutdown waits for scheduler fire handlers before adapter close。
- M7-A09 evidence: deterministic fake NapCat success/disconnected/action-failure traces in `.ai-handoff/evidence/m72/`; real QQ E2E was not run。
- API changes: **NONE**. Schema changes: **NONE**. M7.3 is implemented in the separate bounded-copilot section and awaits external review。
