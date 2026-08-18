# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M4.1 Static Hardening Checkpoint）

- **M3 FINAL = PASS**（External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- **M4 = STATIC_HARDENING_COMPLETE_REAL_ENV_PENDING**
- **M4 FINAL = NOT YET DECLARED**
- **M5 = NOT_AUTHORIZED**
- 本 checkpoint 只提交 M4.1 静态加固 + fresh installed-package isolation 证据；不宣称 Real Provider 或 Real QQ 通过。

## 本轮完成（M4.1 static hardening）

- TaskService 公开 `DEADLINE_UNSET` sentinel：deadline 省略 = 保持不变；显式 `None` = 清除；naive datetime 拒绝（替换内部 `_UNSET`）。
- Agent handler source gate：missing source / disabled source 直接返回安全本地回复，不触发 Agent、不拼接到 LLM 结果。
- Trusted provenance：`AgentContext.user_text` / `ToolContext.user_text`（模型不可控）；`task_create` 的 `source_text_reference` 使用 runtime 信任的用户消息，不再由模型注入。
- ContextBudget：当前用户输入只计一次——已在 live turn 时通过 `_turn_tokens` 计入，不再额外合成/重复计数。
- Provider timeout 独立性：Agent LLM 请求不再派生 tool 超时（`timeout_s=None`，回落 Provider 自身配置）。
- M4 第一版多创建限制契约化：M2 `(source_id, source_message_id)` 唯一约束下，同一 Agent 用户消息最多创建一个 Task；第二次 `task_create` 安全失败。无 schema v3。

## Verification（FRESH PACKAGE ISOLATION — Workspace Agent local evidence）

- 全新隔离环境创建（未复用 `.venv-m4iso` / `.venv-m2iso` / 任何既有 venv / 全局包）。
- 当前工作树以真实安装包形式（non-editable）安装 V2 + test extras 成功；jsonschema 依赖就位。
- Installed-package import origin：**PASS**——imports resolved from fresh environment installed V2 package；无 Legacy root / AstrBot / 旧 venv / PYTHONPATH 泄漏。
- M4.1 focused tests（覆盖 deadline sentinel / explicit clear / Reminder coupling / missing & disabled Source gate / auto_extract=false explicit Agent / ContextBudget single-count / Provider timeout independence / trusted provenance / multi-create limitation / M4 Provider/Agent/Router regressions）：**88 passed**
- Full V2 pytest：**466 passed**
- `python -m compileall -q src tests`：**PASS**
- Anti-AstrBot gate：**PASS**
- `git diff --check`：**PASS**
- Secret/PII diff scan：**PASS**
- These are Workspace Agent local results, not independent External ChatGPT execution。

## Real environment status

- Real Provider Tool Call: **NOT RUN**
- Real QQ Agent E2E: **NOT RUN**
- QQ processes / protected primary account: **NOT TOUCHED**
- No real Provider or QQ PASS is claimed。

## Known limitation / open design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task/Reminder mutations use separate repository commits; temporary inconsistency after a Reminder operation failure can self-heal through startup `resync_all()`。This checkpoint does not redesign M3, add a unit-of-work, or modify Reminder architecture。Re-open only if External ChatGPT explicitly requests it。

## Next gate

External ChatGPT should independently inspect the pushed commit。Real Provider Tool Call and, only if that passes, safe independent-test-bot QQ E2E remain pending。M4 FINAL is not declared。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- No QQ process was stopped, restarted, or modified。
- Fresh virtual environment files are not committed。
