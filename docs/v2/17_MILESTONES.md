# 17_MILESTONES.md

> M1-M7 详细定义与 PASS 标准。**代码存在不算 PASS**；必须达到明确验收。每 Milestone 完成后：真实测试 → 更新项目状态 → checkpoint → push → 外部审核 → 才进入下一个。

## M1：Independent QQ Runtime

**范围**：CampusRuntime / CampusEvent / EventBus / Router / OneBotAdapter / Echo Handler。

**实现**：
- `campuscue/app/runtime.py` 生命周期（07_RUNTIME_LIFECYCLE，M1 只激活 Config/EventBus/Router/OneBotAdapter/Echo）
- `core/events.py` CampusEvent（06_DOMAIN_MODEL 第一版字段：event_id/trace_id/platform/conversation_id/conversation_type/group_id/sender_id/message_id/text/segments）
- `core/bus.py` **有界** asyncio.Queue（`await put` 背压）+ 每事件 Task + 强引用 + 异常隔离 + shutdown drain
- `core/router.py` Guard（valid message / self-message / **transport dedup** / minimal rate）+ Echo Handler
- `adapters/onebot/` **Reverse WebSocket SERVER**（NapCat 为 client 拨入；configurable host/port/path、token 校验、单 active connection + stale replacement、disconnect cleanup）+ converter（纯函数，Event Frame vs Action Response Frame 分类）+ sender（text，echo correlation：unique echo → pending Future → 匹配回帧，timeout/pending cleanup/断连 fail-all）
- `adapters/base.py` PlatformAdapter 边界（start/stop/send/status）

**M1 明确不做**：DB、Task Pipeline、SourceRepository/SourcePolicy（M2 起）、Agent、Reminder、API、WebUI、at/reply/image 发送（仅解析到段）。

**验收（REAL ENV VERIFIED 才 PASS）**：
- 真实 QQ 群发送 `hello`，控制台输出 `platform=onebot conversation_type=group group_id=... sender_id=... message_id=... text=hello`
- QQ 收到 `received: hello`
- **AstrBot 完全不运行**；代码无 `import astrbot`（Anti-AstrBot Gate 扫描通过）
- 隔离数据目录启动成功

## M2：Task Pipeline（含 Provider Foundation）

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

**验收（REAL ENV VERIFIED）**：
- 真实 QQ 提问"我这周有什么事情？" → Agent 真实 Tool Call（task_list）→ TaskService → 真实数据 → 回答（非硬编码）
- max_steps 防呆；重复 tool call 中止；超时/错误分类文案
- 无 Provider 配置时优雅报错（"未配置模型服务"）

## M5：API

**范围**：FastAPI（Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System）+ SSE。

**实现**：按 11_API_SPEC。

**验收**：contract + integration 测试全绿；错误路径（409/422/404）；SSE 生命周期（断连/重连/补拉）测试；默认 loopback。

## M6：WebUI

**范围**：全新 WebUI（首页/任务/消息/日历/AI/接入/模型/设置），Desktop + Mobile，无 Emoji，Lucide 或统一 SVG，非开发者后台风。

**实现**：按 12_WEB_UI_SPEC + Design Tokens（M6 定具体值，配合外部视觉审核）。

**验收**：
- 自动 UI 行为测试（Playwright：桌面 + 390/599/768/1024/1440）通过，无 console error、无横向溢出
- 无障碍自动检查（焦点/alt/label）
- 生成截图 → `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL` → **外部视觉审核通过才 PASS**

## M7：Full E2E

**范围**：完整真实链路。

**验收（REAL ENV VERIFIED）**：
- 真实 QQ："软件杯报名星期三截止。" → 收到 → 自动判断 → 提取 Task → DB → Web 实时出现 → Reminder 建立
- 用户："最近有什么比赛？" → Agent → Tool → TaskService → 回答
- 全程无 AstrBot

## 每 Milestone 后的 Gate

真实测试 → 更新 .ai-handoff（HANDOFF/PROJECT_STATE/STATUS）→ checkpoint（secret scan + 测试）→ commit → push → 远程验证 → 外部 ChatGPT 审核 → 审核通过才进入下一 Milestone。
