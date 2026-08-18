# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy `campuscue/` / `astrbot/` / `dashboard/` frozen/reference

## current_milestone

- M0-M2：**FINAL PASS**
- M3 FINAL：**PASS**（External ChatGPT，baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- M4 = STATIC_HARDENING_COMPLETE_REAL_ENV_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## completed

- M4 implementation：Provider-neutral tool protocol、OpenAI-compatible serialization/parsing、ToolRegistry、trusted ToolContext、source-scoped Task Tools、CampusAgentRuntime、bounded tool loop、conversation/thread lock、conversation LRU cap、CJK ContextBudget hardening、event-timestamp system prompt、router/runtime wiring、configuration/package changes、peer-review regression tests。
- **M4.1 static hardening（本轮）**：TaskService public `DEADLINE_UNSET` sentinel（省略=不变 / 显式 None=清除 / naive 拒绝）；handlers/agent.py missing-source 与 disabled-source gate（不触发 Agent，返回安全本地回复）；AgentContext/ToolContext 增加 trusted `user_text`（`task_create.source_text_reference` 由模型注入改为 runtime 信任值）；ContextBudget 当前用户输入只计一次（已 live turn 不再重复合成）；Provider LLM 请求不再派生 tool 超时（Provider timeout 独立性）；多创建第一版限制契约文档化。

## verified (Workspace Agent local evidence — fresh installed-package isolation environment)

- **Fresh brand-new environment `.venv-m41fresh` created；working-tree V2 installed as a real package（non-editable）with test extras**；未复用任何既有 venv。
- Installed-package import origin：**PASS**——campuscue、campuscue.agents、campuscue.tools、campuscue.providers、campuscue.services、campuscue.storage、campuscue.tasks、campuscue.handlers、campuscue.adapters、campuscue.adapters.onebot、jsonschema 均从 fresh 环境已安装 V2 包解析；无 Legacy root / AstrBot / 旧 venv / PYTHONPATH 泄漏。
- Full V2 pytest：**466 passed**
- M4.1 focused（5 个 M4 测试文件）：**88 passed**
- compileall：**PASS**
- Anti-AstrBot：**PASS**
- git diff --check：**PASS**
- Secret/PII diff scan：**PASS**
- These are local Workspace Agent results, not independent External ChatGPT execution。

## real_environment

- Real Provider Tool Call：**NOT RUN**
- Real QQ Agent E2E：**NOT RUN**
- QQ processes / protected primary account：**NOT TOUCHED**

## known_limitations

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged. A second `task_create` from the same user message is safely returned as failure. No schema v3 was introduced。
- **M3 cross-repository atomicity：KNOWN LIMITATION / OPEN DESIGN RISK（out of scope）**。Task/Reminder temporary inconsistency remains recoverable through startup `resync_all()`。No unit-of-work or Reminder architecture redesign is included。
- M4 final external review is pending。

## next_gate

External ChatGPT independent review of the pushed checkpoint → Real Provider Tool Call → safe independent-test-bot QQ E2E only after Provider pass. M4 FINAL must not be declared by this checkpoint。

## architecture_decisions

- ADR-001 ~ ADR-013 plus M4 decisions in `.ai-handoff/DECISIONS.md`。
