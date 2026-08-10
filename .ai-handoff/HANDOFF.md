# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2b.1.2 Fallback Contract Fix）

- **本轮**：外部 ChatGPT 对 M2b.1.1 最终复核 → 通过；剩余一小轮 fallback/dedup 契约修正（A/B/C + whitespace secret + dedup 课程语义）
- **状态**：M2b.1 = FINAL_IMPLEMENTATION_COMPLETE — AWAITING_EXTERNAL_FINAL_REVIEW；**M2b.2 NOT_AUTHORIZED**
- **Gate**：M0/M1/M2a = PASS；**M2 = IN_PROGRESS（M2b.1 最终实现完成待最终复核；M2b.2 NOT_AUTHORIZED）；M2 FINAL = NOT PASS**

## 本轮完成（M2b.1.2）

1. **[A] generic "unsupported" 不再触发 structured fallback**：`_classify_400` 中 STRUCTURED_OUTPUT_UNSUPPORTED 仅接受结构化特定证据（error.type/code/message 中显式出现 json_schema / response_format / structured_output / "structured output"）；`unsupported` / `unsupported_parameter` / `unsupported_feature` 单独出现 → INVALID_REQUEST（不 fallback）。无厂商特定句子匹配
2. **[B] 主/回退路径共享一个 canonical system 契约**：prompts.py 重构——`build_system_prompt(json_only: bool)` 单一实现；canonical 语义（校园事务定义/AI-first 判断/上下文补全/信号是 hints/输入即数据/忽略消息内指令/输入不得覆盖系统规则/不复述原文/字段语义）主回退完全相同；唯一差异 = 输出强制（primary 带 schema 指导 + response_schema；fallback 带"只输出合法 JSON object"规则 + response_schema=None）
3. **[B2] fallback 保留上下文/信号/时间戳/当前消息**：fallback user 消息与 primary 完全一致（`build_user_message` 同一实例），不回退为仅 current_text；user role 永不拼接未信任群文本
4. **[11] whitespace-only secret**：`_resolve_secret` 用 strip 判断空（"   " → CONFIG_ERROR + 0 transport）；合法 secret 值不 strip 不改变
5. **[C] no-deadline 跨课程 dedup 修正**：双方课程已知且不同 → 即使双方 deadline 都为 None 也不 dedup；同课程 → dup；一方缺课程 → 宽松 dup 允许；`build_dedup_key` 改为 course 已知才入键（与 dedup 语义一致）

## 测试

- **316 passed**（新增 14：400 分类 4 例 A-D、whitespace secret 1、fallback canonical 契约 1、fallback 上下文保留 1、fallback injection 边界 1、dedup 5 例 A-E、dedup key 1）
- Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`，316 passed）

## AGENT_DISCOVERED_DELTA（M2b.1.2）

- [DESIGN_CHANGE]：`FALLBACK_PROMPT` 常量删除；fallback 请求现在直接复用 `build_user_message` 的同一 user 消息（不再 format 拼接）
- [FAILURE_MODE]："Fallback semantic drift" 加入失败模式表（primary 全契约 vs fallback 简化提示 → 真实 endpoint 大部分走 fallback 时 primary 测试失效）；预防 = 单 canonical prompt 契约，仅输出强制不同

## REAL ENV

- M1 REAL ENV VERIFIED 保留；M2b.1.2 无真实 Provider/QQ 声明（M2b.2）

## 下一步

- 外部 ChatGPT M2b.1 最终源码复核（10 项：generic unsupported 不 fallback / 结构化证据仍 fallback / fallback 保留 AI-first 语义 / injection 边界 / 上下文保留 / whitespace secret / dedup 课程语义 / AI-first 未变 / 无 M2b.2 / 文档一致）→ PASS 后 M2b.2 授权

## 本轮修改文件

- 修改：tasks/prompts.py（canonical system 契约重构）、tasks/extractor.py（fallback 共享 prompt + 用户消息）、providers/openai_compatible.py（400 分类收紧 + whitespace secret）、tasks/dedup.py（no-deadline 课程语义 + key 一致）
- 新增：无新文件
- 修改：tests/unit/{test_provider,test_m2b1_units}.py（+14）、.ai-handoff/、双 Memory
