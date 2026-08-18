# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M4.2 Real Provider Tool Call Checkpoint）

- **M3 FINAL = PASS**（External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- **M4.1 STATIC HARDENING = PASS**（External ChatGPT decision at baseline `6e02289d56a0a05bae5db80dd694b05918853959`）
- **M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING**
- **M4 FINAL = NOT YET DECLARED**
- **M5 = NOT_AUTHORIZED**
- 本 checkpoint：真实 Provider M4 Tool Calling 验收 PASS；QQ/NapCat 未触碰；M4 FINAL 不声明；QQ E2E 下一门但本 checkpoint 不运行。

## 本轮验收（REAL PROVIDER TOOL CALL — PASS）

- **Provider**：provider_type=openai_compatible；model=deepseek-chat；base_url host=api.deepseek.com；secret_reference=CAMPUSCUE_LLM_API_KEY（secret 值永不存储/打印）。
- **真实链路**（临时 DB 全新创建、合成数据、无 mock transport）：真实 Provider 自主发出 `task_list`（scope 由模型选择，实测 week/today）→ ToolRegistry 执行 → TaskService → 临时真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → 最终回答反映合成 DB 任务。模型还自主追加 `task_get` 深入查询。
- **数据驱动证明**：通过 TaskService 将任务标题改为"…-已更新"后第二次查询，最终回答反映新标题；Source B 任务在 Source A 会话中零泄漏，反之亦然（source-scoped）。
- **暴露并修复的真实兼容性 bug**：真实 DeepSeek 在 tool-call 轮次同时返回辅助 content 文本 + tool_calls；原 `_parse_ok` 将其硬判为 `MALFORMED_OUTPUT`（M4 §8 "两种明确形状"设计未考虑真实端点行为）。最小修复：tool_calls 权威，辅助文本丢弃（保证 Agent loop 仍只有 final-text / tool-call 两种明确形状）；新增 `test_6b_mixed_content_and_tool_calls_keeps_tool_calls` 覆盖新契约。
- **修复后回归**：M4 focused **88 passed**；full V2 **466 passed**（fresh installed-package `.venv-m42fresh` 重装后全量验证）；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS。

## Verification（Workspace Agent local evidence — fresh installed-package isolation）

- 新建 fresh 环境 `.venv-m42fresh`（源码变更后按要求重做 package isolation）；working-tree V2 以真实安装包（non-editable）+ test extras 安装；imports resolved from fresh environment installed V2 package；无 Legacy/AstrBot/旧 venv/PYTHONPATH 泄漏。
- Full V2 pytest：**466 passed**；M4.1 focused：**88 passed**。
- These are Workspace Agent local results, not independent External ChatGPT execution。

## Real environment status

- Real Provider Tool Call: **PASS**（2026-08-18）
- Real QQ Agent E2E: **NOT RUN（下一门；本 checkpoint 未授权运行）**
- QQ processes / protected primary account: **NOT TOUCHED**
- No QQ/NapCat acceptance claim is made in this checkpoint。

## Known limitation / open design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task/Reminder mutations use separate repository commits; temporary inconsistency after a Reminder operation failure can self-heal through startup `resync_all()`。This checkpoint does not redesign M3, add a unit-of-work, or modify Reminder architecture。Re-open only if External ChatGPT explicitly requests it。

## Next gate

External ChatGPT should independently inspect the pushed commit（重点：`_parse_ok` mixed 响应修复 + 验收证据）。Then safe independent-test-bot QQ Agent E2E is the next gate — DO NOT run it in this checkpoint。M4 FINAL is not declared。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- Acceptance used only synthetic data in a temporary SQLite DB（deleted after run）；acceptance DB not committed。
- No QQ process was started, stopped, or modified。
- Fresh virtual environment files are not committed。
