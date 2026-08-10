# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2b.1.1 Real-Gate Hardening）

- **本轮**：外部 ChatGPT 对 M2b.1（AI-first）源码复核 → PASS_WITH_FIXES（8 项 fix：A-G + 所有权/去重/注入防御等），执行 Real-Gate Hardening
- **状态**：M2b.1.1 完成 — AWAITING_EXTERNAL_FINAL_REVIEW；**M2b.2 NOT_AUTHORIZED**
- **Gate**：M0/M1/M2a = PASS；M2b.1 = AI_FIRST_PIPELINE_HARDENED AWAITING_EXTERNAL_FINAL_REVIEW；**M2 = IN_PROGRESS（M2b.2 NOT_AUTHORIZED）；M2 FINAL = NOT PASS**

## 本轮完成（M2b.1.1 Real-Gate Hardening）

1. **[A] 缺 secret env fail-before-transport**：`_resolve_secret()` 配置了 secret_reference 但 env 缺失/空 → `ProviderError CONFIG_ERROR`，**0 transport calls**；不打印 secret、不静默变成远程 401（tests：missing/empty/valid Bearer）
2. **[B] Extraction 记录 provider/model**：`BaseProvider.model` 公共属性（业务不再碰 `_model`）；pipeline 传递 `provider_type` + `model` 到所有 L1/L3 Extraction（task_created/model_said_none/duplicate/provider_error 均记录；无 provider 时为 null）
3. **[C] model_said_none 审计保留 reason/confidence**：`ExtractionResult` 新增 confidence/reason（has_task=false 时）；normalized_result 含 `has_task/confidence/reason`；不虚构 Task、不保留 title/course；不持久化完整输入 context；system prompt 已要求不复述原文
4. **[D] schema fallback 仅 structured_output_unsupported**：新 `ProviderErrorCode.STRUCTURED_OUTPUT_UNSUPPORTED`；`_classify_400` 用 HTTP 结构化错误字段（error.type/code/message）做通用分类（无厂商特定字符串）；generic INVALID_REQUEST/AUTH/RATE/TIMEOUT/NETWORK/MODEL/CONTEXT → 不 fallback（tests：unsupported→2 calls；generic 400→1 call；auth→1 call；timeout→1 call）
5. **[E] ContextCollector window resize**：buffer 按当前配置的 context_window 重建（deque.maxlen 变更即 resize，保留已有消息；缩容安全）；cross-source 隔离保留
6. **[F] 显式年份不 auto-roll**：仅无年份的过去日期允许跨年推断；"2026年8月5日"/"2026-08-05"（当前 2026-08-10）→ past rejected，绝不变成 2027
7. **[G] test DB 隔离 fail-fast**：`load_config()` 新增 `_validate_task_config`——CAMPUSCUE_ENV=test + pipeline enabled + 无显式 CAMPUSCUE_DB_PATH → ConfigError（启动前 fail）；`database_path_explicit` 记录 provenance；confidence_threshold 必须有限且 ∈[0,1]；timezone 必须 ZoneInfo 可解析
8. **[H] TaskService 所有权清理**：移除 `_confidence_threshold` 与死 `decide_pending_confirm()`；状态判定归 Pipeline（L4/L6），TaskService 只应用 candidate.pending_confirm；TaskPipeline 移除死 `_dedup`（不再碰 `task_service._tasks` 私有）
9. **[I] dedup_key 单一 helper**：`dedup.py::build_dedup_key(title, course, deadline)` 为唯一 canonical 存储键（normalized title + course 双方已知 + deadline minute）；Deduplicator 语义一致；无模糊匹配
10. **[J] prompt-injection defense-in-depth**：system prompt 新增输入安全规则（消息是数据非指令、忽略消息内指挥、输入不得覆盖 schema/系统规则）；测试证明 user 文本永远在 user role、固定 system prompt + schema（mock 行为测试，非"LLM 注入已解决"声明）

## 测试

- **302 passed**（新增 M2b.1.1 回归：secret 3、结构化分类 3、extractor provider-neutral 3、model_said_none 2、fallback 分类 2、time 4、dedup key 4、resize 3、config 7、ownership 2、pipeline 审计 6 ≈ 38 断言组）
- Anti-AstrBot PASS；package isolation PASS（fresh venv `.venv-m2iso`，302 passed）

## AGENT_DISCOVERED_DELTA（M2b.1.1）

- [DESIGN_CHANGE]：CONFIG_ERROR 与 STRUCTURED_OUTPUT_UNSUPPORTED 两个新 ProviderErrorCode；400 分类顺序：context → structured-evidence → model（避免 "invalid json_schema for model X" 误判 INVALID_MODEL）
- [PRIVACY_DELTA]：model_said_none 的 Extraction 行 `confidence` 列持久化模型自报置信度（0.5 默认只用于 has_task=true 分支；has_task=false 缺省为 None 不虚构）
- [REVIEW_REQUEST 更新]：18 项审核点 → 10 项 M2b.1.1 复核点

## REAL ENV

- M1 REAL ENV VERIFIED 保留；M2b.1.1 无真实 Provider/QQ 声明（M2b.2）

## 下一步

- 外部 ChatGPT M2b.1.1（Real-Gate Hardening）最终源码复核（10 项审核点）→ PASS 后 M2b.2 授权

## 本轮修改文件

- 修改：providers/{errors,base,openai_compatible}.py（CONFIG_ERROR/STRUCTURED_OUTPUT_UNSUPPORTED/model 属性/secret fail-fast/400 分类）、tasks/{extractor,prompts,context,dedup,time_normalizer,models,pipeline}.py、services/task_service.py、config.py、app/runtime.py
- 新增：tests/integration/test_m2b11_hardening.py（17 tests）
- 修改：tests/unit/{test_provider,test_m2b1_units}.py、tests/integration/test_m2b1_ai_first.py、.ai-handoff/、双 Memory
