# REVIEW_REQUEST.md

> M2b.1.1（Real-Gate Hardening）最终审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M2b.1.1）复核本轮 10 项修复。

## 背景

外部 ChatGPT 已对 M2b.1（AI-first，ADR-013）源码复核 → **AI-FIRST PRODUCT DIRECTION = PASS；Core pipeline = PASS_WITH_FIXES**。本轮为 narrow REAL-GATE hardening（不改 AI-first 行为、不恢复 semantic gating、不开始真实 Provider/QQ）。

## 请求审核内容（10 项 M2b.1.1 复核点）

1. **Missing-secret fail-before-transport**：secret_reference 配置但 env 缺失/空 → `ProviderError(CONFIG_ERROR)`，**0 transport calls**；secret 值不打印；不静默转远程 401。测试：missing→CONFIG_ERROR+0 calls；empty→0 calls；valid→`Authorization: Bearer <值>`
2. **Extraction provider/model 审计**：`BaseProvider.model` 公共属性（业务不碰 `_model`）；pipeline 在 task_created/model_said_none/duplicate/provider_error 记录 provider_type+model；无 provider 时为 null
3. **model_said_none 审计**：保留 confidence/reason/raw/structured_mode；不虚构 Task 对象、不保留 title/course；**不持久化完整输入 context**；normalized_result 恰为 `{has_task, confidence, reason}`
4. **Schema fallback 分类**：仅 `STRUCTURED_OUTPUT_UNSUPPORTED`（HTTP 结构化错误字段通用分类，无厂商字符串）→ 恰一次 fallback；generic INVALID_REQUEST / AUTH / RATE / TIMEOUT / NETWORK / MODEL / CONTEXT → 不 fallback；总 calls ≤ 2
5. **ContextCollector resize**：context_window 1→3 后缓冲区可增长（重建 deque，保留现有消息）；缩容安全；cross-source 隔离
6. **显式年份不 auto-roll**：仅无年份过去日期可跨年；"2026年8月5日"/"2026-08-05" → past rejected（reason `past_rejected:explicit_date`），绝不 2027
7. **Test DB 隔离 fail-fast**：`CAMPUSCUE_ENV=test` + pipeline + 无显式 `CAMPUSCUE_DB_PATH` → 启动前 `ConfigError`；显式 tmp 路径 → pass；生产默认仍允许；confidence_threshold ∈[0,1] 有限；timezone ZoneInfo 可解析
8. **TaskService 所有权清理**：`decide_pending_confirm()` 已删除；`_confidence_threshold` 已移除；TaskService 只应用 `candidate.pending_confirm`；TaskPipeline 死 `_dedup` 与 `task_service._tasks` 私有访问已移除
9. **dedup_key 一致性**：单一 canonical `build_dedup_key(title, course, deadline)`；same semantic→same key；不同 course→不同 key；不同 deadline minute→不同 key；无模糊匹配
10. **Prompt-injection defense-in-depth**：system prompt 输入安全规则；mock 测试证明 user 文本永在 user role、固定 system prompt+schema（**防御纵深声明，不宣称 LLM 注入已解决**）

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN；REAL QQ M2：NOT RUN（M2b.2 验收）
- [UNVERIFIED_HYPOTHESIS] 真实 Provider（如 Ark）json_schema 支持度与真实 token 成本（M2b.2 确认；成本可观测性留未来）
- prompt-injection 测试是 contract/mock 级证明（防御纵深），不宣称真实 LLM 注入免疫
- submission_method 无专属列（CURRENT M2 LIMITATION）

## Real Verified vs Not

- **CONFIRMED（Workspace Agent）**：302 tests 全绿、fresh venv 隔离 `.venv-m2iso`（+tzdata）、Anti-AstrBot、secret fail-fast 0 transport、fallback 分类 ≤2 calls、resize/年份/去重键/配置 fail-fast 回归
- **NOT VERIFIED**：真实 Provider 调用、真实 QQ 任务抽取

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
