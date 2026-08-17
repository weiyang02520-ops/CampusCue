# REVIEW_REQUEST.md

# CampusCue M4 Checkpoint — External Review Request

## Gate state

- M3 FINAL = **PASS** (External ChatGPT decision at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`)
- M4 implementation = **COMPLETE**
- M4 = IMPLEMENTATION_COMPLETE_REAL_ENV_PENDING
- M4 FINAL = NOT YET DECLARED
- M5 = NOT_AUTHORIZED

## Scope delivered

Please independently inspect the pushed M4 implementation for:

1. Provider-neutral tool-call contract and OpenAI-compatible boundary serialization/parsing。
2. ToolRegistry registration, JSON Schema validation, timeout, exception sanitization。
3. Trusted ToolExecutionContext and source/conversation isolation。
4. Task Tools and TaskService-only mutations preserving Reminder lifecycle。
5. CampusAgentRuntime bounded loop, max steps, duplicate-call defense and ContextBudget。
6. Conversation per-thread serialization lock and LRU thread cap。
7. CJK-aware conservative token estimate and event-timestamp system prompt。
8. Deterministic group @self/private activation and Agent-before-TaskPipeline routing。
9. CampusRuntime composition and M4 configuration/package changes。
10. Peer-review regression tests and package/Anti-AstrBot compatibility。

## Local evidence (Workspace Agent only)

- Full V2 pytest: **453 passed**
- M4 Provider/Agent/Router focused: **44 passed**
- compileall: **PASS**
- Anti-AstrBot: **PASS**
- git diff --check: **PASS**
- These results were run locally by the Workspace Agent; they are not independent External ChatGPT execution。

## Real environment (not run)

- Real Provider Tool Call: **NOT RUN**
- Real QQ Agent E2E: **NOT RUN**
- QQ processes / protected primary account: **NOT TOUCHED**

Do not mark M4 FINAL PASS based on mock transport tests. Real Provider acceptance and safe independent-test-bot QQ acceptance remain separate gates.

## Known limitation / open design risk

M3 Task and Reminder mutations still cross separate repository commits. Temporary inconsistency after a Reminder operation failure is recoverable by startup `resync_all()`. This checkpoint intentionally does not redesign M3, add a unit-of-work, or change Reminder architecture. Re-open only with an explicit external request.

## Privacy

No real QQ IDs, group IDs, chat content, tokens, Provider secrets, or protected-account process actions are included in this checkpoint.

## Visual review

No UI/visual output in M4.
