# 17_MILESTONES.md

> M1-M7 详细定义与 PASS 标准。**代码存在不算 PASS**；必须达到明确验收。每 Milestone 完成后：真实测试 → 更新项目状态 → checkpoint → push → 外部审核 → 才进入下一个。

## M1：Independent QQ Runtime

**范围**：CampusRuntime / CampusEvent / EventBus / Router / OneBotAdapter / Echo Handler。

**实现**：
- `campuscue/app/runtime.py` 生命周期（07_RUNTIME_LIFECYCLE）
- `core/events.py` CampusEvent（06_DOMAIN_MODEL 第一版字段：event_id/trace_id/platform/conversation_id/conversation_type/group_id/sender_id/message_id/text/segments）
- `core/bus.py` asyncio.Queue + 每事件 Task + 强引用 + 异常隔离
- `core/router.py` Guard（self-message/source-enabled/rate limit 简化）+ Echo Handler
- `adapters/onebot/` client(WS server) + converter（纯函数）+ sender（text）
- `adapters/base.py` PlatformAdapter 边界（start/stop/send/status）

**明确不做**：Task Pipeline、Agent、Reminder、API、WebUI、at/reply/image 发送（仅解析到段）。

**验收（REAL ENV VERIFIED 才 PASS）**：
- 真实 QQ 群发送 `hello`，控制台输出 `platform=onebot conversation_type=group group_id=... sender_id=... message_id=... text=hello`
- QQ 收到 `received: hello`
- **AstrBot 完全不运行**；代码无 `import astrbot`（Anti-AstrBot Gate 扫描通过）
- 隔离数据目录启动成功

## M2：Task Pipeline

**范围**：SourcePolicy / Prefilter / ContextCollector / LLM Extraction / TimeNormalizer / Dedup / TaskRepository / TaskService / SQLite。

**实现**：见 10_TASK_PIPELINE + 09_STORAGE（sources/tasks/extractions 表）。

**验收（REAL ENV VERIFIED）**：
- 真实 QQ："高数第三章作业周五晚上12点前交学习通。" → 数据库产生正确 Task（title=第三章作业、category=homework、course=高等数学、deadline=本周五 23:59 +08:00、source_text_reference 保留）
- 同消息重发 → 去重（dedup_key 命中，不重复创建）
- 消息页可见 extraction 记录与"为何创建/为何未创建"
- LLM mock 路径有测试（B13 修复）

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

## M4：Agent

**范围**：BaseProvider / OpenAICompatibleProvider / ProviderManager / ToolDefinition / ToolRegistry / CampusAgentRuntime / Task Tools。

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
