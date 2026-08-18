# REVIEW_REQUEST.md

# CampusCue M4.2 Real Provider Tool Call Checkpoint — External Review Request

## Gate state

- M3 FINAL = **PASS** (baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`)
- M4.1 STATIC HARDENING = **PASS** (baseline `6e02289d56a0a05bae5db80dd694b05918853959`)
- M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## What was proven (Real Provider Tool Call — PASS)

A REAL configured Provider performed the M4 Tool Calling protocol end-to-end against real CampusCue services and a real temporary SQLite DB:

1. Provider: openai_compatible, model=deepseek-chat, real httpx transport to api.deepseek.com (secret via `secret_reference` env mechanism; secret value never stored/printed)。
2. The model **autonomously emitted** `task_list` tool calls（scope=week / today，由模型选择）; no hardcoded dispatch, no mock transport, no scripted LLMResponse。
3. ToolRegistry executed `task_list` → TaskService → real SQLite returned the seeded synthetic task → tool result returned to the provider → **second real Provider call** produced a natural-language final answer reflecting the DB task。
4. Data-driven proof: title changed through TaskService → second query → answer changed accordingly。
5. Source scope: Source A answer excluded Source B's task and vice versa (each query returned exactly its own source's data)。
6. The model additionally autonomously called `task_get` — further evidence of non-hardcoded model-driven tool use。

## Source fix included (smallest focused fix)

Real OpenAI-compatible endpoints（DeepSeek observed）may return auxiliary `content` text alongside `tool_calls` in the same message。CampusCue's `_parse_ok` previously classified this as `MALFORMED_OUTPUT`。Fixed: `tool_calls` is authoritative; the auxiliary text is dropped（the Agent loop keeps exactly two unambiguous shapes: final text OR tool calls）。Test `test_6b_mixed_content_and_tool_calls_keeps_tool_calls` covers the new contract。

Please review: `v2/src/campuscue/providers/openai_compatible.py`（`_parse_ok`）、`v2/tests/unit/test_m4_provider_tools.py`（test_6b）、`docs/v2/08_PROVIDER_AND_AGENT.md`。

## Local evidence (Workspace Agent only)

- Real Provider transport: PASS（HTTP 200; provider emitted tool_calls; tool id present; arguments parsed）
- Temporary SQLite: YES；Synthetic Source/Task: YES（seeded through TaskService; no raw SQL）
- Focused M4 tests: **88 passed**; Full V2: **466 passed**（fresh installed-package `.venv-m42fresh`）
- compileall: PASS; Anti-AstrBot: PASS; git diff --check: PASS; Secret/PII scan: PASS
- These results are local Workspace Agent evidence, not independent External ChatGPT execution。

## Not run / not touched

- Real QQ Agent E2E: **NOT RUN（next gate；not authorized in this checkpoint）**
- QQ processes / protected primary account: **NOT TOUCHED**
- No QQ/NapCat claim of any kind is made。

## Known limitation / design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task/Reminder mutations still cross separate repository commits; startup `resync_all()` recovery accepted。Not redesigned in this checkpoint。

## Privacy

No real QQ IDs, group IDs, chat content, tokens, Provider secrets, local private paths, or protected-account process actions are included。Acceptance used only synthetic data in a temporary DB（deleted）; no acceptance DB committed。Fresh virtual environment files are not committed。

## Visual review

No UI/visual output in M4。
