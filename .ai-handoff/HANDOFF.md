# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2b.2 REAL ENV ACCEPTANCE COMPLETE）

- **本轮**：M2b.2 真实环境验收——真实 QQ 群消息 → NapCat（Framework）→ Reverse WS → CampusCue AI-first pipeline → 真实 DeepSeek Provider → TimeNormalizer/Dedup/TaskService → 真实 SQLite，测试 A-E 全部 PASS
- **状态**：M2b.2 = REAL_ENV_ACCEPTANCE_COMPLETE — AWAITING_EXTERNAL_M2_FINAL_REVIEW；**M2 FINAL = NOT PASS（等外部复核）**
- **Gate**：M0/M1/M2a/M2b.1 = PASS；M2b.2 验收完成；**M3 NOT_AUTHORIZED**

## 本轮完成（M2b.2 + NapCat Recovery）

1. **[REAL ENV] Provider preflight**：`ProviderManager.test_default()` 真实 DeepSeek `deepseek-chat` 通过（DNS/TLS/auth/endpoint/parse）；真实 TaskExtractor structured_mode=**json_fallback**（DeepSeek 拒绝 json_schema → CampusCue 正确回退，共享 canonical 语义契约，≤2 calls）
2. **[REAL ENV] 测试 A（M1 共存）**：真实群消息 `hello` → `received: hello`（send_group_msg retcode 0）；M2 pipeline 启用时 M1 Echo 正常
3. **[REAL ENV] 测试 B（明确任务）**：`数第三章作业周五晚上12点前交学习通` → Task 创建（title=第三章作业，category=homework，course=null——消息原文无课程名，模型正确，deadline=`2026-08-14 15:59 UTC` 精确，status=pending，confidence=0.95）
4. **[REAL ENV] 测试 C（普通聊天）**：`hello` 同时被 AI-first 检查 → skipped Extraction（has_task=false，confidence=0.95，reason），无 Task，无输入文本泄漏（normalized/audit 均无消息原文）
5. **[REAL ENV] 测试 D（语义重复）**：`高数第三章作业周五晚上12点前交学习通。` → duplicate（`same_semantic_task`），Task 数保持 1；该次模型提取 course=高等数学（消息含课程名）——REAL_MODEL_VARIANCE 记录
6. **[REAL ENV] 测试 E（重启持久化）**：仅重启 CampusCue（不碰 QQ/NapCat）→ NapCat 2 秒内自动重连（`onebot client connected`）；Task 仍在（DB 持久化）
7. **[NAPCAT RECOVERY]**：Framework 前台启动 EPIPE → **stdout 重定向启动成功**；WS 断开（`Object has been destroyed`）→ 新会话重连恢复；**用户大号保护**（误杀后已还原配置，测试全部用独立小号 bot）

## 测试

- **316 passed**（全量回归，M1 87 旧全绿）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`）
- REAL ENV 证据：见上（MACHINE_CONFIRMED + USER_CONFIRMED：用户贴出群聊记录含 hello/任务消息时间线）

## AGENT_DISCOVERED_DELTA（M2b.2）

- [REAL_PROVIDER_FACT]：DeepSeek `deepseek-chat` 实测 **json_fallback**（json_schema 不支持）；fallback 路径共享 canonical 语义契约验证（l3 structured_mode=json_fallback）
- [REAL_QQ_FACT]：NapCat Framework 注入启动需 stdout 重定向（否则 EPIPE）；QQ 账号自动登录记忆会导致注入启动登入最近账号（需用户手动选 bot）
- [REAL_PIPELINE_FACT]：完整链路真实验证——source_text_reference 精确保留原文（含首字缺失原文"数第三章"），TimeNormalizer 精确（`2026-08-14 15:59 UTC`），去重 `same_semantic_task`
- [REAL_MODEL_BEHAVIOR]：course 提取依赖消息原文是否含课程名（REAL_MODEL_VARIANCE，非 bug）
- [PRIVACY_OBSERVATION]：model_said_none 行 normalized_result/audit 无输入文本；raw_result 为模型输出（含模型复述的字段）——符合当前设计
- [RECOMMENDED_MEMORY_PROMOTION]：见 CHATGPT_MEMORY §9M（SAFETY_CONSTRAINT/EXECUTION_SAFETY/ACCOUNT_IDENTITY/NAPCAT/M2/PROVIDER/AI_FIRST/DEDUP/M1_COMPAT）

## REAL ENV

- **M2b.2 REAL ENV VERIFIED**（2026-08-10）：真实 QQ 群消息全链路（NapCat Framework + 小号 bot + DeepSeek + SQLite）
- 用户大号：**PROTECTED**（未再触碰；配置已还原默认）；测试全部用独立小号 bot

## 下一步

- 外部 ChatGPT M2 最终复核（读取 GitHub HEAD + REAL ENV 证据）→ PASS 后 M3（Reminder）授权

## 本轮修改文件

- 源码：**零修改**（无 CampusCue source changes）
- 文档：v2/README.md（NapCat 重定向启动 runbook 事实）、docs/context/ 双 Memory、.ai-handoff/（HANDOFF/PROJECT_STATE/REVIEW_REQUEST/STATUS/CHANGELOG）
