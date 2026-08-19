# REVIEW_REQUEST.md

# CampusCue M4.3 Real QQ Agent E2E Checkpoint — External Review Request

## Gate state

- M3 FINAL = **PASS** (baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`)
- M4.1 STATIC HARDENING = **PASS** (baseline `6e02289d56a0a05bae5db80dd694b05918853959`)
- M4.2 REAL PROVIDER TOOL CALL = **PASS** (Workspace Agent local evidence, baseline `3c1b5ab55843a4fb01020e07d785e1eedf4ea9f7`)
- M4.3 REAL QQ AGENT E2E = **PASS** (Workspace Agent local evidence, 2026-08-19)
- M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## What was proven (Real QQ Agent E2E — PASS)

A REAL QQ group message reached CampusCue through an independent NapCat Shell Windows Node environment and completed the full M4 Agent loop:

1. NapCat: official **v4.18.19** `NapCat.Shell.Windows.Node.zip` (SHA256 verified), fresh directory `C:\Tools\NapCat\m43-clean`; `NAPCAT_DISABLE_MULTI_PROCESS=1`; missing `crypto.dll`/`ssl.dll` copied from official local QQ install; native wrapper load PASS; TEST_BOT login via QR (quick login required hand-Q verification).
2. Real group message `@TEST_BOT 我这周有什么事情？` → OneBot Reverse WS `ws://127.0.0.1:6199/ws` → CampusCue (task pipeline + Agent enabled, real SQLite `m4-qq-accept.db`, DeepSeek key from Windows Credential Manager, never printed).
3. @self Agent activation → real DeepSeek autonomously emitted `task_list` → ToolRegistry → TaskService → real SQLite → tool result returned → second real Provider call → `send_group_msg` retcode 0 → real QQ received the task list.
4. Data-driven proof: via production TaskService, a synthetic task was changed from “高等数学第三章作业/高等数学” to “线性代数第四章作业/线性代数”; the second real QQ query response showed the updated title — answer follows SQLite data.
5. Non-@ normal group message did **not** activate Agent: no Agent tool loop, no reply; only the M2 AI-first TaskPipeline LLM extraction ran and recorded `has_task=false` / `status=skipped` (this is not an Agent Provider call).

## Local evidence (Workspace Agent only)

- Real NapCat + TEST_BOT + Reverse WS + CampusCue + real DeepSeek + real SQLite: PASS
- Data-change verification: PASS
- Non-@ no-Agent verification: PASS
- M4 focused tests: **88 passed**; Full V2: **466 passed** (fresh installed-package `.venv-m42fresh`, M4.2 historical evidence)
- compileall: PASS; Anti-AstrBot: PASS; git diff --check: PASS; Secret/PII scan: PASS
- These results are local Workspace Agent evidence, not independent External ChatGPT execution。

## Not run / not touched

- M4 FINAL: NOT DECLARED
- M5: NOT_AUTHORIZED
- No main-account QQ data was modified; NapCat independent environment did not inject system QQ.
- No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or local private paths are included in this request.

## Known limitation / design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task/Reminder mutations still cross separate repository commits; startup `resync_all()` recovery accepted。Not redesigned in this checkpoint。

## Visual review

No UI/visual output in M4.
