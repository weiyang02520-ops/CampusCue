# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2b.1 AI-First Task Extraction Pipeline）

- **本轮**：按用户产品决策将 M2b.1 重写为 AI-first（本地规则不再做语义 gate）
- **状态**：M2b AI_FIRST_PIPELINE_IMPLEMENTATION_COMPLETE — AWAITING_EXTERNAL_REVIEW
- **Gate**：M0/M1/M2a = PASS；**M2 = IN_PROGRESS（M2b.1 完成待复核；M2b.2 NOT_AUTHORIZED）；M2 FINAL = NOT PASS**

## 本轮完成（AI-first 改造）

1. **[USER_STATED][PRODUCT_DECISION]**：优先少漏校园事务 > 极限省 token；enabled + auto_extract Source 的正常自然语言消息原则上都交给 LLM
2. **prefilter.py → 双组件**：MessageHygieneFilter（仅 high-certainty 垃圾 hard drop：empty/空白/超长/无文本）+ LocalSignalAnalyzer（hints：deadline/time/action/affair/authority/coursework；score 绝不 gate）
3. **pipeline 流程**：L0 SourcePolicy → L1 Hygiene → L1.5 Signals（hints 进 prompt）→ L2 Context → L3 LLM 单次 triage+extraction（≤2 calls 硬上限）→ L4 确定性校验+Time → L5 Dedup → L6 Confidence → L7 TaskService → SQLite
4. **prompts**：AI-first 语义判断（结合上下文、不完整消息可提取）；signal hints 仅参考
5. **隐私**：model_said_none 审计不保存完整输入 context；只有创建 Task 才存 source_text_reference
6. **ADR-013** 创建；config 移除 prefilter_threshold（signal 不 gate）

## 测试

- **264 passed**（AI-first 新增 7：低分进 Provider、模糊上下文解析、普通闲聊→skipped、垃圾 hard drop 0 provider、单次调用、fallback ≤2 calls）
- 全部旧测试按 AI-first 语义修正（audit 键 local_signals；l1_drop → hygiene_drop）
- package isolation PASS（fresh venv）；Anti-AstrBot PASS

## AGENT_DISCOVERED_DELTA（AI-first）

- [DESIGN_CONFLICT]：旧 audit 键 l1 → local_signals；旧 L1 prefilter gate 语义整体 SUPERSEDED（ADR-013）
- [TEST_FACT]：模糊消息（"这个周五前交一下"等 4 条）现在必须到达 LLM——已加强制回归
- [UNVERIFIED_HYPOTHESIS]：真实 Provider（如 Ark）json_schema 支持度与真实成本（M2b.2 确认；token 成本可观测性留未来）

## REAL ENV

- M1 REAL ENV VERIFIED 保留；M2b.1 无真实 Provider/QQ 声明（M2b.2）

## 下一步

- 外部 ChatGPT M2b.1（AI-first）源码复核（18 项审核点）→ PASS 后 M2b.2 授权

## 本轮修改文件

- 修改：tasks/prefilter.py（Hygiene+Signals）、tasks/pipeline.py（AI-first 流程）、tasks/extractor.py（hints + ≤2 calls）、tasks/prompts.py（AI-first）、config.py（去 prefilter_threshold）
- 新增：tests/integration/test_m2b1_ai_first.py（7）、docs/v2/adr/ADR-013_AI_FIRST_EXTRACTION.md
- 修改：tests（旧 prefilter/l1_drop 语义）、10/17/18、双 Memory、.ai-handoff/
