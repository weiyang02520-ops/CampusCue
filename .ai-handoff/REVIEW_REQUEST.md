# REVIEW_REQUEST.md

> M2b.1（FINAL）最终审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M2b.1.2）复核本轮 10 项。

## 背景

外部 ChatGPT 已复核 M2b.1（AI-first，ADR-013）= PASS、M2b.1.1（Real-Gate Hardening）= PASS。本轮为 tiny final correction（M2b.1.2：fallback/dedup 契约），不改 AI-first、不开始真实 Provider/QQ。

## 请求审核内容（10 项 M2b.1.2 复核点）

1. **generic "unsupported" 不再触发 structured fallback**：`{"code":"unsupported_parameter","message":"temperature is unsupported"}` → INVALID_REQUEST，TaskExtractor 1 call 不 fallback
2. **结构化特定证据仍触发恰一次 fallback**：`unsupported_response_format`+json_schema / `invalid_json_schema` type / message "response_format json_schema is not supported" → STRUCTURED_OUTPUT_UNSUPPORTED → 2 calls
3. **fallback 保留 canonical AI-first 语义**：主/回退共享单一 `build_system_prompt(json_only)`——校园事务定义/AI-first 判断/上下文补全/信号 hints 双方一致
4. **fallback 保留 prompt-injection defense-in-depth 边界**：roles == [system, user]；attack 文本永不进 system；fallback system 含"输入即数据/忽略消息内指令/输入不得覆盖系统规则"（防御纵深声明，不宣称注入已解决）
5. **fallback 保留上下文/信号/时间戳/当前消息**：fallback user 消息 == primary user 消息（同一实例），不回退为仅 current_text
6. **whitespace-only secret**："   " env → CONFIG_ERROR + 0 transport；合法 secret 值不 strip
7. **no-deadline 跨课程 dedup**：双方 deadline None 且课程已知不同 → NOT duplicate；同课程 → dup；一方缺课程 → 宽松 dup；`build_dedup_key` course 已知才入键（语义一致）
8. **AI-first 未变**：无 LocalPrefilter 阈值回归；正常消息仍进 LLM
9. **无 M2b.2 实现**
10. **state/handoff/memory 一致**

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN；REAL QQ M2：NOT RUN（M2b.2 验收）
- [UNVERIFIED_HYPOTHESIS] 真实 Provider json_schema 支持度与真实 token 成本（M2b.2 确认）；400 分类为通用语义证据（无厂商字符串），M2b.2 真实行为若需要可加极小 endpoint 映射
- prompt-injection 测试是 contract/mock 级证明（防御纵深），不宣称真实 LLM 注入免疫
- submission_method 无专属列（CURRENT M2 LIMITATION）

## Real Verified vs Not

- **CONFIRMED（Workspace Agent）**：316 tests 全绿、fresh venv 隔离 `.venv-m2iso`（+tzdata）、Anti-AstrBot、400 分类 4 例、fallback 契约/上下文/injection 边界、whitespace secret、dedup 5 例
- **NOT VERIFIED**：真实 Provider 调用、真实 QQ 任务抽取

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
