# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy `campuscue/` / `astrbot/` / `dashboard/` frozen/reference

## current_milestone

- M0-M3：**FINAL PASS**
- M4.1 STATIC HARDENING：**PASS**（External ChatGPT，baseline `6e02289d56a0a05bae5db80dd694b05918853959`）
- M4.2 REAL PROVIDER TOOL CALL：**PASS**（Workspace Agent local evidence，baseline `3c1b5ab55843a4fb01020e07d785e1eedf4ea9f7`）
- M4.3 REAL QQ AGENT E2E：**PASS**（Workspace Agent local evidence，2026-08-19）
- M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## completed

- M4 implementation：Provider-neutral tool protocol、OpenAI-compatible serialization/parsing、ToolRegistry、trusted ToolContext、source-scoped Task Tools、CampusAgentRuntime、bounded tool loop、conversation/thread lock、conversation LRU cap、CJK ContextBudget hardening、event-timestamp system prompt、router/runtime wiring、configuration/package changes、peer-review regression tests。
- M4.1 static hardening：TaskService public `DEADLINE_UNSET` sentinel；Agent handler missing/disabled source gate；trusted `user_text` provenance；ContextBudget current-input single count；Provider timeout independence；multi-create first-version limitation documented。
- M4.2 Real Provider Tool Call：真实 DeepSeek `deepseek-chat` 端到端 M4 Tool Calling 验收 PASS；真实兼容性 bug 修复（tool_calls 权威、辅助文本丢弃）。
- **M4.3 Real QQ Agent E2E（本轮）**：真实 QQ 群消息 `@TEST_BOT 我这周有什么事情？` → @self Agent 激活 → 真实 DeepSeek 自主 `task_list` → ToolRegistry → TaskService → 真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → `send_group_msg` retcode 0 回复任务列表；通过生产 TaskService 修改任务标题后，第二次真实查询回复随 SQLite 数据变化；普通不 @ 群消息不触发 Agent（无 Agent tool loop、无回复；仅 M2 AI-first extraction 判 skipped）。

## verified (Workspace Agent local evidence)

- **M4.3 Real QQ Agent E2E**：**PASS**（真实 NapCat Shell Windows Node v4.18.19 + TEST_BOT + Reverse WS + CampusCue + 真实 DeepSeek + 真实 SQLite；数据驱动变化验证通过；普通消息不触发 Agent 验证通过）
- Full V2 pytest：**466 passed**（fresh installed-package `.venv-m42fresh`，M4.2 历史证据）
- M4 focused：**88 passed**
- compileall：**PASS**（M4.2 历史证据）
- Anti-AstrBot：**PASS**
- git diff --check：本轮执行
- Secret/PII scan：本轮执行
- These are local Workspace Agent results, not independent External ChatGPT execution。

## real_environment

- Real Provider Tool Call：**PASS**（2026-08-18）
- Real QQ Agent E2E：**PASS**（2026-08-19）
- NapCat 独立环境：`C:\Tools\NapCat\m43-clean`（官方 NapCat.Shell.Windows.Node v4.18.19；未注入系统 QQ；TEST_BOT 登录态由人类扫码建立）
- CampusCue runtime：`v2\.venv-m42fresh` + `CAMPUSCUE_TASK_PIPELINE=1` + `CAMPUSCUE_AGENT=1` + `data/m4-qq-accept.db`

## known_limitations

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged. A second `task_create` from the same user message is safely returned as failure. No schema v3 was introduced。
- **M3 cross-repository atomicity：KNOWN LIMITATION / OPEN DESIGN RISK（out of scope）**。Task/Reminder temporary inconsistency remains recoverable through startup `resync_all()`。No unit-of-work or Reminder architecture redesign is included。
- M4 final external review is pending。

## next_gate

External ChatGPT independent review of the pushed checkpoint（重点：M4.3 真实 QQ E2E 证据 + NapCat Shell Node 独立环境准备）。M4 FINAL must not be declared by this checkpoint。

## architecture_decisions

- ADR-001 ~ ADR-013 plus M4 decisions in `.ai-handoff/DECISIONS.md`。
