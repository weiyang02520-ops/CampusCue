# HANDOFF.md

> M0.2 FINAL CONSISTENCY FIX 交接记录。由工作区 AI 在 checkpoint 前更新。

## 本轮目标

执行 M0.2：修复外部复核发现的 4 个残留一致性问题、写入 MEMORY DELTA、语义一致性检查、checkpoint 后 STOP。**未创建任何 V2 正式代码。**

## 本轮完成

### 外部复核修复（4 项）

| # | 问题 | 修改 |
|---|---|---|
| 1 | 07_RUNTIME_LIFECYCLE 失败隔离残留"指数退避重连"（client 思维） | 改为 server 语义：detect disconnect → 清理 stale 连接 → fail/清理 pending action futures → server 保持监听 → 等 NapCat 重连 → 接受新连接 → 替换 stale → resume；日志限频。注明 SSE 等未来 client 模块不在此列 |
| 2 | 05_V2_ARCHITECTURE "任务流（M2 范围）"含 L8/L9，与 10/17 矛盾 | 改为 "任务流 — progressive activation"：L0-L7 [ACTIVE FROM M2]、L8 [M3]、L9 [M5]；明确 M2 不实现 Reminder/Realtime、TaskService 钩子惰性接线 |
| 3 | CHATGPT_MEMORY CURRENT TRUTH 维护动态 HEAD `6480ad2`（已过期为 `3d70da1`） | 删除动态 HEAD 字段，改为 "RESOLVE FROM GIT/GITHUB AT RECOVERY TIME"；历史 checkpoint commit（6480ad2/3d70da1）保留在 HISTORY；AGENT_MEMORY 未新增动态 HEAD 字段 |
| 4 | 08_PROVIDER_AND_AGENT M2 LLMRequest 含 tool_schema（ToolSet 转换后）→ 阶段依赖混乱 | LLMRequest 改 M2 最小集合（messages/model/temperature/max_tokens/timeout/structured output/disable_thinking），**无 ToolSet/ToolRegistry/ToolDefinition/AgentRuntime 依赖**；LLMResponse.tool_calls 标注 M4 EXTENSION / inactive until M4；OpenAICompatibleProvider tools 传入标注 M4 EXTENSION |

### MEMORY DELTA 写入（4 条）

- **[EXTERNAL_REVIEW][CORRECTION]**：consistency scan 必须比较同一概念在多个 canonical docs 的语义，不能只搜关键词（M0.1 漏跨文件语义冲突教训）
- **[EXTERNAL_REVIEW][DESIGN_DECISION]**：Long-term Memory 不维护动态 Git HEAD；recovery 时从 Git/GitHub 获取；Memory 只记里程碑 commit/历史基线
- **[EXTERNAL_REVIEW][CORRECTION]**：OneBot Reverse WS——CampusCue server 等 NapCat client 重连，不 outbound exponential reconnect
- **[EXTERNAL_REVIEW][CORRECTION]**：M2 Provider Foundation 不依赖 M4 Tool System

两 Memory 均已写入（CHATGPT_MEMORY §9A + HISTORY/时间线；AGENT_MEMORY rules 11-13 + §7 新增失败模式 + §18 M2/M4 提醒）。

## 实际修改文件

- docs/v2/07_RUNTIME_LIFECYCLE.md（Fix 1）
- docs/v2/05_V2_ARCHITECTURE.md（Fix 2）
- docs/context/CHATGPT_MEMORY.md（Fix 3 + §9A + 时间线）
- docs/context/AGENT_MEMORY.md（rules 11-13 + §7 + §18）
- docs/v2/08_PROVIDER_AND_AGENT.md（Fix 4）
- .ai-handoff/：PROJECT_STATE / STATUS / HANDOFF / REVIEW_REQUEST / CHANGELOG_AI（本轮全部更新）

## 真实测试

- 无代码变更，无测试运行（M0.2 纯文档）
- 执行验证：跨文档语义一致性检查（8 概念：Reverse WS ownership / OneBot reconnect / M2 scope / M3 Reminder / M5 Realtime / Provider Foundation / Tool activation / Git HEAD source of truth × 8 文件：04/05/07/08/10/17/CHATGPT_MEMORY/AGENT_MEMORY）、Memory health check、Anti-AstrBot 表述一致性、secret scan、git diff inspection
- **确认：未创建任何正式 V2 source code**

## Mock Tests / 未验证

- 未运行任何测试（无被测代码）
- 未做真实 QQ / NapCat 联调（M1 验收）

## AGENT_DISCOVERED_DELTA（W 协议）

None beyond externally requested M0.2 corrections.

（本轮全部变更来自外部复核 finding；无新增仓库事实/设计冲突/运行时发现。）

## Known Bugs

- V1 审计发现 B12（时区硬编码）、B13（LLM 测试缺口）已入 13_BUG_LESSONS.md，M2 修

## Architecture Changes / Decisions

- M0.2 修复 4 项（见上表）；Memory 语义规则（动态 HEAD 不维护）已入双 Memory

## Branch / Remote / Base

- 仓库：weiyang02520-ops/CampusCue（public）
- 本次提交：docs: finalize M0 consistency and memory semantics
- Base：3d70da1（M0.1 commit）

## External Review Focus

- 见 REVIEW_REQUEST.md（4 项残留修复对照 + Memory health + 语义一致性）
