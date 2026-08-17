# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。Git HEAD/remote 状态由 Git 实时获取。

## project

- 名称：CampusCue V2（课讯）
- 定位：校园事务管理 + AI Agent + QQ 自动信息入口
- V2 implementation root：`v2/`；Legacy `campuscue/` / `astrbot/` / `dashboard/` frozen/reference

## current_milestone

- M0-M2：**FINAL PASS**
- M3 FINAL：**PASS**（External ChatGPT，baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- M4 = IMPLEMENTATION_COMPLETE_REAL_ENV_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## completed

- M4 implementation：Provider-neutral tool protocol、OpenAI-compatible serialization/parsing、ToolRegistry、trusted ToolContext、source-scoped Task Tools、CampusAgentRuntime、bounded tool loop、conversation/thread lock、conversation LRU cap、CJK ContextBudget hardening、event-timestamp system prompt、router/runtime wiring、configuration/package changes、peer-review regression tests。

## verified (Workspace Agent local evidence)

- Full V2 pytest：**453 passed**
- M4 Provider/Agent/Router focused：**44 passed**
- compileall：**PASS**
- Anti-AstrBot：**PASS**
- git diff --check：**PASS**
- These are local Workspace Agent results, not independent External ChatGPT execution。

## real_environment

- Real Provider Tool Call：**NOT RUN**
- Real QQ Agent E2E：**NOT RUN**
- QQ processes / protected primary account：**NOT TOUCHED**

## known_limitations

- **M3 cross-repository atomicity：KNOWN LIMITATION / OPEN DESIGN RISK（out of scope for this checkpoint）**。Task/Reminder temporary inconsistency remains recoverable through startup `resync_all()`。No unit-of-work or Reminder architecture redesign is included。
- M4 final external review is pending。

## next_gate

External ChatGPT independent review of the pushed checkpoint → Real Provider Tool Call → safe independent-test-bot QQ E2E only after Provider pass. M4 FINAL must not be declared by this checkpoint。

## architecture_decisions

- ADR-001 ~ ADR-013 plus M4 decisions in `.ai-handoff/DECISIONS.md`。
