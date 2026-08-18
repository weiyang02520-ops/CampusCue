# REVIEW_REQUEST.md

# CampusCue M4.1 Static Hardening Checkpoint — External Review Request

## Gate state

- M3 FINAL = **PASS** (External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`)
- M4 = STATIC_HARDENING_COMPLETE_REAL_ENV_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## Scope delivered (M4.1 static hardening)

Please independently inspect the pushed M4.1 hardening for:

1. TaskService public `DEADLINE_UNSET` sentinel — omitted deadline keeps unchanged; explicit `None` clears; naive datetime rejected。
2. Agent handler missing-source / disabled-source gates return safe local replies without triggering the Agent。
3. Trusted provenance — `AgentContext.user_text` / `ToolContext.user_text` are runtime-controlled; `task_create.source_text_reference` no longer model-injected。
4. ContextBudget current-input single count — live current turn is counted exactly once; no duplicated synthesis。
5. Provider timeout independence — Agent LLM request no longer derives tool timeout。
6. M4 first-version multi-create limitation contract (documented, no schema v3)。
7. M4 Provider/Agent/Router regression coverage。

## Local evidence (Workspace Agent only — fresh installed-package isolation)

- Brand-new isolated environment created；working-tree V2 installed as a real package (non-editable) with test extras。
- Installed-package import origin：**PASS**（campuscue.agents / campuscue.tools / jsonschema 均从 fresh 环境已安装 V2 包解析；无 Legacy/AstrBot/旧 venv 泄漏）。
- Full V2 pytest: **466 passed**
- M4.1 focused: **88 passed**
- compileall: **PASS**
- Anti-AstrBot: **PASS**
- git diff --check: **PASS**
- Secret/PII diff scan: **PASS**
- These results were run locally by the Workspace Agent; they are not independent External ChatGPT execution。

## Real environment (not run)

- Real Provider Tool Call: **NOT RUN**
- Real QQ Agent E2E: **NOT RUN**
- QQ processes / protected primary account: **NOT TOUCHED**

Do not mark M4 FINAL PASS based on mock transport tests. Real Provider acceptance and safe independent-test-bot QQ acceptance remain separate gates。

## Known limitation / design risk

- **[DESIGN_LIMITATION][M4]**：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second `task_create` from the same user message is safely returned as failure。No schema v3 was introduced。
- M3 Task and Reminder mutations still cross separate repository commits。Temporary inconsistency after a Reminder operation failure is recoverable by startup `resync_all()`。This checkpoint intentionally does not redesign M3, add a unit-of-work, or change Reminder architecture。Re-open only with an explicit external request。

## Privacy

No real QQ IDs, group IDs, chat content, tokens, Provider secrets, local private paths, or protected-account process actions are included in this checkpoint。Fresh virtual environment files are not committed。

## Visual review

No UI/visual output in M4。
