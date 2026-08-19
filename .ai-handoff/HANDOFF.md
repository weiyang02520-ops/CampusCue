# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M4.3 Real QQ Agent E2E Checkpoint）

- **M3 FINAL = PASS**（External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`）
- **M4.1 STATIC HARDENING = PASS**（External ChatGPT decision at baseline `6e02289d56a0a05bae5db80dd694b05918853959`）
- **M4.2 REAL PROVIDER TOOL CALL = PASS**（Workspace Agent local evidence at baseline `3c1b5ab55843a4fb01020e07d785e1eedf4ea9f7`）
- **M4.3 REAL QQ AGENT E2E = PASS**（Workspace Agent local evidence，2026-08-19）
- **M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW**
- **M4 FINAL = NOT YET DECLARED**
- **M5 = NOT_AUTHORIZED**
- 本 checkpoint：真实 QQ Agent E2E 完成；M4 FINAL 不声明；等待 External ChatGPT 独立审核。

## 本轮验收（REAL QQ AGENT E2E — PASS）

- **独立 NapCat 环境**：官方 NapCat.Shell.Windows.Node v4.18.19（GitHub NapNeko/NapCatQQ Release，SHA256 校验通过），目录 `C:\Tools\NapCat\m43-clean`；`NAPCAT_DISABLE_MULTI_PROCESS=1` 启动，避免 worker `--no-sandbox` bad-option；补齐 `crypto.dll`/`ssl.dll` 后 native module load PASS；TEST_BOT 登录（quick login 因手Q 验证回退二维码，人类扫码）。
- **真实链路**：真实 QQ 群消息 `@TEST_BOT 我这周有什么事情？` → NapCat → Reverse WS `ws://127.0.0.1:6199/ws` → CampusCue → @self Agent 激活 → 真实 DeepSeek 自主发出 `task_list` → ToolRegistry → TaskService → 真实 SQLite（`v2/data/m4-qq-accept.db`）→ tool result 回传 → 第二次真实 Provider 调用 → `send_group_msg` retcode 0 → QQ 收到任务列表。
- **数据驱动证明**：通过生产 TaskService 将合成任务“高等数学第三章作业/高等数学”改为“线性代数第四章作业/线性代数”；第二次真实 QQ 查询回复显示“线性代数第四章作业”，回答随 SQLite 数据变化。
- **普通消息不触发 Agent**：不 @ 的日常群消息无 Agent tool loop、无回复；仅 M2 AI-first TaskPipeline 调用 Provider 判定 `has_task=false` / `status=skipped`（符合 ADR-013，不是 Agent Provider 调用）。

## Verification（Workspace Agent local evidence）

- M4.3 真实验收为 Workspace Agent local evidence，非独立 External ChatGPT 执行。
- M4 focused **88 passed**；full V2 **466 passed**（fresh installed-package `.venv-m42fresh`，M4.2 历史证据）。
- compileall PASS；Anti-AstrBot PASS（M4.2 历史证据）。
- git diff --check PASS；Secret/PII scan PASS（本轮执行）。

## Real environment status

- Real Provider Tool Call: **PASS**（2026-08-18）
- Real QQ Agent E2E: **PASS**（2026-08-19）
- NapCat 独立环境：`C:\Tools\NapCat\m43-clean`
- CampusCue runtime：`v2\.venv-m42fresh`，`CAMPUSCUE_TASK_PIPELINE=1` + `CAMPUSCUE_AGENT=1`，DB `v2/data/m4-qq-accept.db`

## Known limitation / open design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task/Reminder mutations use separate repository commits; temporary inconsistency after a Reminder operation failure can self-heal through startup `resync_all()`。This checkpoint does not redesign M3, add a unit-of-work, or modify Reminder architecture。Re-open only if External ChatGPT explicitly requests it。

## Next gate

External ChatGPT should independently inspect the pushed checkpoint（重点：M4.3 真实 QQ E2E 证据 + NapCat Shell Node 独立环境准备）。M4 FINAL is not declared。

## Privacy / safety

- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are recorded here。
- Acceptance used only synthetic tasks in the local acceptance DB（`m4-qq-accept.db`）；NapCat runtime data and acceptance DB are not committed。
- NapCat 独立环境不注入系统 QQ；TEST_BOT 登录态由人类扫码建立；未触碰主号。
- Fresh virtual environment files are not committed。
