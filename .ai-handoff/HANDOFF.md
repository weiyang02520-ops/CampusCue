# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M4 Agent Checkpoint）

- **M3 FINAL = PASS**（External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- **M4 = IMPLEMENTATION_COMPLETE_REAL_ENV_PENDING**
- **M4 FINAL = NOT YET DECLARED**
- **M5 = NOT_AUTHORIZED**
- 本 checkpoint 只提交当前本地 M4 implementation；不宣称 Real Provider 或 Real QQ 通过。

## 本轮完成

- Provider-neutral tool-call extension：`LLMToolSchema` / `LLMToolCall` / assistant tool-call and tool-result messages。
- OpenAI-compatible tool serialization/parsing remains inside the Provider boundary；mixed text/tool-call responses and missing tool-call IDs are rejected。
- `ToolDefinition` / `ToolResult` / `ToolRegistry`：duplicate-name fail-fast、JSON Schema validation、timeout and sanitized errors。
- Trusted `ToolContext` and source/conversation scoped Task Tools：`task_list`、`task_get`、`task_create`、`task_update`、`task_complete`、`task_dismiss`、`reminder_list`。
- All Agent mutations continue through the shared `TaskService`; M3 reminder lifecycle coupling is preserved。
- `CampusAgentRuntime` bounded tool loop、max steps、duplicate-call defense、ContextBudget、bounded in-memory conversation。
- Per-thread conversation lock；conversation LRU capacity cap；conservative CJK token estimate；event timestamp used for Agent system prompt。
- Group explicit @self activation、private activation、Agent-before-TaskPipeline router ordering、shared CampusRuntime composition。
- M4 configuration and explicit package list updates。
- Peer-review regression tests and relevant Memory/Handoff state updates。

## Verification (Workspace Agent local evidence)

- Full V2 pytest: **453 passed**
- M4 Provider/Agent/Router focused: **44 passed**
- `python -m compileall -q src tests`: **PASS**
- Anti-AstrBot gate: **PASS**
- `git diff --check`: **PASS**
- Package list includes `campuscue.tools` and `campuscue.agents`。
- These are Workspace Agent local results, not independent External ChatGPT execution。

## Real environment status

- Real Provider Tool Call: **NOT RUN**
- Real QQ Agent E2E: **NOT RUN**
- QQ processes / protected primary account: **NOT TOUCHED**
- No real Provider or QQ PASS is claimed。

## Known limitation / open design risk (M3, out of scope)

Task and Reminder mutations use separate repository commits. A temporary inconsistency after a Reminder operation failure can self-heal through startup `resync_all()`. This checkpoint does **not** redesign M3, add a unit-of-work, or modify Reminder architecture. Re-open only if External ChatGPT explicitly requests it。

## Next gate

External ChatGPT should independently inspect the pushed commit. Real Provider Tool Call and, only if that passes, safe independent-test-bot QQ E2E remain pending. M4 FINAL is not declared。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, or Provider secrets are recorded here。
- No QQ process was stopped, restarted, or modified。
