# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy `campuscue/` / `astrbot/` / `dashboard/` frozen/reference

## current_milestone

- M0-M2：**FINAL PASS**
- M3 FINAL：**PASS**（External ChatGPT，baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- M4.1 STATIC HARDENING：**PASS**（External ChatGPT，baseline `6e02289d56a0a05bae5db80dd694b05918853959`）
- M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## completed

- M4 implementation：Provider-neutral tool protocol、OpenAI-compatible serialization/parsing、ToolRegistry、trusted ToolContext、source-scoped Task Tools、CampusAgentRuntime、bounded tool loop、conversation/thread lock、conversation LRU cap、CJK ContextBudget hardening、event-timestamp system prompt、router/runtime wiring、configuration/package changes、peer-review regression tests。
- M4.1 static hardening：TaskService public `DEADLINE_UNSET` sentinel；Agent handler missing/disabled source gate；trusted `user_text` provenance；ContextBudget current-input single count；Provider timeout independence；multi-create first-version limitation documented。
- **M4.2 Real Provider Tool Call（本轮）**：真实 DeepSeek `deepseek-chat` 端到端 M4 Tool Calling 验收 PASS——模型自主 `task_list`（+自主 `task_get`）→ ToolRegistry → TaskService → 临时真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → 最终回答反映合成 DB 数据；改 title 后回答变化；Source A/B 作用域隔离验证通过。修复真实兼容性 bug：真实 OpenAI 兼容端点（DeepSeek）tool-call 轮次同时返回辅助 content + tool_calls，原 `_parse_ok` 硬判 MALFORMED_OUTPUT → 最小修复（tool_calls 权威，辅助文本丢弃），新增/更新 provider 解析测试。

## verified (Workspace Agent local evidence)

- **Real Provider Tool Call**：**PASS**（真实 httpx transport；无 mock、无硬编码分发；模型自主选择 scope=week 等参数；tool_call id/参数解析 PASS；两次真实 Provider 调用链完整）。
- Full V2 pytest：**466 passed**（fresh installed-package `.venv-m42fresh`）
- M4 focused：**88 passed**
- Fresh installed-package import origin：**PASS**（campuscue.agents / campuscue.tools / jsonschema 均从 fresh 环境已安装 V2 包解析；无 Legacy/AstrBot/旧 venv/PYTHONPATH 泄漏）
- compileall：**PASS**
- Anti-AstrBot：**PASS**
- git diff --check：**PASS**
- Secret/PII scan：**PASS**
- These are local Workspace Agent results, not independent External ChatGPT execution。

## real_environment

- Real Provider Tool Call：**PASS**（2026-08-18）
- Real QQ Agent E2E：**NOT RUN（下一门，本 checkpoint 不运行）**
- QQ processes / protected primary account：**NOT TOUCHED**

## known_limitations

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged. A second `task_create` from the same user message is safely returned as failure. No schema v3 was introduced。
- **M3 cross-repository atomicity：KNOWN LIMITATION / OPEN DESIGN RISK（out of scope）**。Task/Reminder temporary inconsistency remains recoverable through startup `resync_all()`。No unit-of-work or Reminder architecture redesign is included。
- M4 final external review is pending。

## next_gate

External ChatGPT independent review of the pushed checkpoint → safe independent-test-bot QQ Agent E2E（Real Provider 已过；QQ E2E 是本 checkpoint 之后的下一门，未授权在本 checkpoint 运行）。M4 FINAL must not be declared by this checkpoint。

## architecture_decisions

- ADR-001 ~ ADR-013 plus M4 decisions in `.ai-handoff/DECISIONS.md`。
