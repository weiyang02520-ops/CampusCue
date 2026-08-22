# CHANGELOG_AI.md

> AI 变更日志（供后续模型追历史，不依赖聊天记录）。

## 2026-08-09 · M0

- **任务**：M0 Architecture / Audit（研究 AstrBot 固定基准 + 审计 V1 + V2 设计文档）
- **Commit**：`6480ad2` docs: M0 architecture audit documents
- **主要修改**：docs/v2/（00-19 + adr/ADR-001~010）；.ai-handoff/ 初版
- **测试**：无（M0 无代码）
- **审核状态**：PASS 方向 / CHANGES_REQUESTED 精度 → 转 M0.1

## 2026-08-09 · M0.1 REVIEW FIX

- **任务**：修复外部审核 14 项 finding + 建立双 Memory + 更新 handoff
- **Commit**：docs: apply M0 external review and bootstrap AI memory（本轮）
- **主要修改**：
  - B~N 14 项修复（见 HANDOFF.md 修复表）：llm 耦合、stop 顺序、Platform 契约、Reverse WS server 所有权、echo 帧关联、有界队列、transport dedup、Guard 范围、Provider 前移 M2、M2 仓储、删消息页验收、阶段激活、Runtime 激活表、Outbound 直连
  - docs/context/CHATGPT_MEMORY.md + AGENT_MEMORY.md（双 Memory 首建）
  - .ai-handoff/ 6 文件更新（含 AGENT_DISCOVERED_DELTA = None beyond corrections）
- **测试**：无（纯文档）；一致性检查 + secret scan 已执行；确认零 V2 代码
- **审核状态**：M0 = PASS（条件），M1 = READY_NOT_STARTED，等待外部审核确认

## 2026-08-09 · M0.2 FINAL CONSISTENCY FIX

- **任务**：修复外部复核 4 项残留 + MEMORY DELTA 写入 + 语义一致性检查
- **Commit**：docs: finalize M0 consistency and memory semantics（本轮）
- **主要修改**：
  - 07：失败隔离改 Reverse WS server 语义（无 outbound 指数退避）
  - 05：任务流改 progressive activation（L0-L7 M2 / L8 M3 / L9 M5）
  - CHATGPT_MEMORY：动态 HEAD 反模式修复（recovery 时从 Git 获取；里程碑 commit 留 HISTORY）+ §9A 新增 4 条 MEMORY DELTA
  - AGENT_MEMORY：rules 11-13 + §7 新增"文档一致性假绿"失败模式 + §18 M2/M4 提醒
  - 08：M2 Provider Foundation 与 M4 Tool System 解耦（LLMRequest 无 ToolSet 依赖；tool_calls/tools 标 M4 EXTENSION）
  - .ai-handoff/ 5 文件更新（AGENT_DISCOVERED_DELTA = None beyond corrections）
- **测试**：无（纯文档）；跨文档语义一致性检查（8 概念×8 文件）+ Memory health check + secret scan 已执行；确认零 V2 代码
- **审核状态**：M0 = AWAITING FINAL EXTERNAL CONFIRMATION；M1 = READY_NOT_STARTED

## 2026-08-09 · M1 INDEPENDENT QQ RUNTIME

- **任务**：实现完全独立的 QQ 最小运行闭环（M1）
- **Commit**：feat: implement independent M1 QQ runtime（本轮）
- **主要修改**：
  - 新增 `v2/` 独立 implementation root（ADR-011）：`v2/src/campuscue/`（core/events、core/bus 有界队列+并发、core/router、core/outbound、handlers/echo、adapters/base、adapters/onebot/{adapter,converter,protocol,dedup}、app/runtime、config、__main__）+ `v2/tests/` + `v2/scripts/check_no_astrbot.py`
  - 新增 docs/v2/adr/ADR-011_V2_CODE_ISOLATION.md；更新 18_DECISIONS、04_ONEBOT_PIPELINE（canonical dedup + 帧分类表）、17_MILESTONES（M1 验收语义）
  - 双 Memory：§9B 新增 7 条 MEMORY DELTA；.ai-handoff/ 6 文件更新
- **测试**：UNIT 49 + INTEGRATION 16 = **65 passed**；PACKAGE ISOLATION PASS（fresh venv）；Anti-AstrBot Gate PASS
- **REAL ENV**：**NOT VERIFIED**（本机无 NapCat）→ M1 = IMPLEMENTED_AWAITING_REAL_ENV
- **审核状态**：等待外部 M1 审核 + 真实 NapCat 联调

## 2026-08-09 · M1.1 RUNTIME CORRECTNESS FIX

- **任务**：修复外部源码审核 8 项 correctness/boundedness/protocol 问题
- **Commit**：fix: harden M1 runtime lifecycle and backpressure（本轮）
- **主要修改**：adapter（stale finally 竞态 + semaphore backpressure + path 校验）、runtime（outbound 进 handler）、config（fail-fast）、protocol（严格响应校验）、converter（移除 raw_message）、__main__（诊断模式去假 claim）
- **测试**：87 passed（新增 22）；package isolation PASS；Anti-AstrBot Gate PASS
- **REAL ENV**：NOT VERIFIED（本机无 NapCat）
- **审核状态**：等待外部 M1.1 复核 → M1.2 Real Env Gate

## 2026-08-10 · M1.2 REAL ENVIRONMENT VERIFICATION

- **任务**：真实 QQ/NapCat 验收（M1 唯一剩余 Gate）
- **Commit**：test: verify M1 with real NapCat QQ environment（本轮）
- **主要修改**：新增 v2/README.md（runbook）；Memory §9D；.ai-handoff/ 6 文件。v2/src 零修改
- **REAL ENV**：**VERIFIED**（NapCat v4.18.18 + 真实 QQ：私聊/群聊 hello→received:hello、非 hello 无回复、重启自动重连、token 握手成功、messagePostFormat=array 兼容）
- **测试**：87 passed 保持；package isolation PASS；Anti-AstrBot PASS
- **审核状态**：M1 = PASS（REAL ENV VERIFIED）；等待外部 M1 最终审核

## 2026-08-10 · M1.3 CONTINUITY & PRIVACY CLEANUP

- **任务**：外部审核确认 M1 技术全部 PASS 后，执行连续性/隐私清理（8 项 finding）
- **Commit**：docs: finalize M1 handoff and privacy cleanup（本轮）
- **主要修改**：
  - PII 脱敏：M1.2 HANDOFF 中的真实 Bot QQ 标识符（NapCat 配置文件名）→ onebot11_<BOT_QQ_REDACTED>.json；测试群名称脱敏
  - CHATGPT_MEMORY：顶部 CURRENT TRUTH 修复为 M1 PASS 后状态 + §9E 5 条 MEMORY DELTA + §14 更新
  - AGENT_MEMORY：Gate 矛盾修复（M2 NOT_AUTHORIZED）+ §7 新增 PII 泄漏失败模式
  - v2/README.md：补 Git Bash MSYS_NO_PATHCONV=1 workaround + PowerShell/Git Bash 分块
  - HANDOFF：重构为 canonical（不再 append-only）
- **测试**：87 passed 保持（无源码改动）；Anti-AstrBot PASS；package isolation PASS
- **PRIVACY_NOTE**：真实 QQ 标识符曾进 M1.2 历史提交；当前 HEAD 已脱敏；历史未重写（需显式授权）
- **审核状态**：M1 = PASS；M1.3 AWAITING_EXTERNAL_REVIEW；M2 NOT_AUTHORIZED

## 2026-08-10 · M2a DATA & PROVIDER FOUNDATION

- **任务**：实现 M2a（数据层 + Provider 基础），供 M2b Task Pipeline 使用
- **Commit**：feat: add M2 data and provider foundation（本轮）
- **主要修改**：
  - ADR-012 契约锁定 7 项（TaskStatus/Source 身份/L2 上下文/Provider 默认/secret_reference/UTC）
  - storage/（SQLAlchemy 2.x + aiosqlite；Database pragma+schema 版本；UTCDateTime；models 4 表+版本表）
  - repositories/（Source/Task/Extraction/ProviderConfig 单表 CRUD；唯一约束防重复）
  - services/source_service.py；providers/（base/models/errors/openai_compatible/manager）+ scripts/m2_configure_provider.py
  - pyproject +3 运行时依赖（sqlalchemy/aiosqlite/httpx）
- **测试**：新增 52（storage 29 + provider 23）；全量 **139 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior verification 保留）；真实 Provider 验收留 M2b
- **审核状态**：M2a AWAITING_EXTERNAL_REVIEW；M2b NOT_AUTHORIZED

## 2026-08-10 · M2a.1 FOUNDATION CORRECTNESS FIX

- **任务**：修复外部源码审核 6 项 finding + 3 项契约补全
- **Commit**：fix: harden M2 data and provider foundation（本轮）
- **主要修改**：provider.test 真实路径、timeout 契约生效、枚举 repository+CHECK 双层、schema 预检零变更、Clock 注入、secret_reference 共享校验、get_by_id、严格成功解析、状态先分类
- **测试**：新增 47 → **186 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior 保留）
- **审核状态**：M2a.1 AWAITING_EXTERNAL_REVIEW；M2b NOT_AUTHORIZED

## 2026-08-10 · M2a.2 FINAL FOUNDATION CLEANUP

- **任务**：修复外部审核最终 7 项 finding（A-G）
- **Commit**：fix: finalize M2 foundation contracts（本轮）
- **主要修改**：secret_reference 单一规则（去重复 regex）、validate_provider_config_numeric 持久化前拒绝、request override 传输前校验、ORM 去墙钟默认（时间戳 required）、HANDOFF/PROJECT_STATE canonical 修复
- **测试**：新增 17 → **203 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior 保留）
- **审核状态**：M2a AWAITING_EXTERNAL_FINAL_REVIEW；M2b NOT_AUTHORIZED

## 2026-08-10 · M2b.1 TASK EXTRACTION PIPELINE

- **任务**：实现 M2b.1（L0-L7 任务抽取 + Mock Provider + SQLite）
- **Commit**：feat: implement M2 task extraction pipeline（本轮）
- **主要修改**：tasks 包（source_policy/prefilter/context/extractor/time_normalizer/dedup/pipeline/models/prompts）+ TaskService + Runtime 可选启用 + tzdata 平台依赖 + m2_configure_source.py
- **测试**：新增 53 → **256 passed**；全链路 Mock → SQLite Task 行验证；并发去重 1 Task；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior 保留；真实 Provider/QQ 留 M2b.2）
- **审核状态**：M2b.1 AWAITING_EXTERNAL_REVIEW；M2b.2 NOT_AUTHORIZED

## 2026-08-10 · M2b.1 AI-FIRST REWRITE

- **任务**：按用户产品决策将 M2b.1 重写为 AI-first（ADR-013）
- **Commit**：feat: implement AI-first M2 task pipeline（本轮）
- **主要修改**：prefilter → HygieneFilter + SignalAnalyzer（hints 不 gate）、pipeline AI-first 流程、extractor 单次调用 + ≤2 calls、prompts AI-first、config 去 prefilter_threshold、ADR-013
- **测试**：新增 7（低分进 Provider/模糊上下文/单次调用/fallback 上限）→ **264 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M2b.2）
- **审核状态**：M2b.1 AWAITING_EXTERNAL_REVIEW；M2b.2 NOT_AUTHORIZED

## 2026-08-10 · M2b.1.1 REAL-GATE HARDENING

- **任务**：外部审核 PASS_WITH_FIXES 的 Real-Gate 硬化轮（不改 AI-first；不开始真实 Provider/QQ）
- **Commit**：fix: harden AI-first pipeline for real provider gate（本轮）
- **主要修改**：
  - providers：secret env 缺失/空 → CONFIG_ERROR（0 transport）；新错误码 STRUCTURED_OUTPUT_UNSUPPORTED（HTTP 结构化字段通用分类）；BaseProvider.model 公共属性
  - tasks：extractor fallback 仅 structured 不兼容（≤2 calls）；model_said_none 保留 confidence/reason；ContextCollector window resize；显式年份不 auto-roll；build_dedup_key 单一 helper；prompt-injection 防御纵深
  - services/task_service：去 _confidence_threshold 与死 decide_pending_confirm（状态判定归 Pipeline）
  - config：test + pipeline + 无 DB_PATH → ConfigError；confidence ∈[0,1]；timezone 可解析
  - pipeline：移除死 _dedup；Extraction 记录 provider/model
- **测试**：新增 38 断言组（secret/fallback 分类/审计 provider-model/model_said_none/resize/年份/dedup key/config/ownership/injection/fake provider）→ **302 passed**；package isolation PASS（.venv-m2iso）；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior 保留；真实 Provider/QQ 留 M2b.2）
- **审核状态**：M2b.1 = AWAITING_EXTERNAL_FINAL_REVIEW；M2b.2 NOT_AUTHORIZED

## 2026-08-10 · M2b.1.2 FALLBACK CONTRACT FIX

- **任务**：外部最终复核通过 M2b.1.1 后，tiny final correction（fallback/dedup 契约）
- **Commit**：fix: align M2 fallback and dedup contracts（本轮）
- **主要修改**：
  - providers/openai_compatible：STRUCTURED_OUTPUT_UNSUPPORTED 仅结构化特定证据（json_schema/response_format/structured_output 显式引用）；generic unsupported 单独出现 → INVALID_REQUEST；whitespace-only secret → CONFIG_ERROR
  - tasks/prompts：单一 canonical `build_system_prompt(json_only)`（主/回退共享语义+安全契约；仅输出强制不同）；删除 FALLBACK_PROMPT 双定义
  - tasks/extractor：fallback 复用同一 user 消息（上下文/信号/时间戳/当前消息保留）；user role 永不拼接群文本
  - tasks/dedup：no-deadline 时课程双方已知且不同 → 不 dedup；build_dedup_key course 已知才入键
- **测试**：新增 14（400 分类 A-D 4、whitespace secret 1、fallback canonical 1、fallback 上下文 1、fallback injection 1、dedup A-E 5、dedup key 1）→ **316 passed**；package isolation PASS（.venv-m2iso）；Anti-AstrBot PASS
- **REAL ENV**：无新声明（M1.2 prior 保留；真实 Provider/QQ 留 M2b.2）
- **审核状态**：M2b.1 = FINAL_IMPLEMENTATION_COMPLETE AWAITING_EXTERNAL_FINAL_REVIEW；M2b.2 NOT_AUTHORIZED

## 2026-08-10 · M2b.2 REAL ENV ACCEPTANCE

- **任务**：M2b.2 真实环境验收（REAL QQ → NapCat → WS → pipeline → Provider → SQLite）+ NapCat Recovery（EPIPE/断开恢复 + 大号保护）
- **Commit**：test: verify M2 with real provider and QQ environment（本轮）
- **主要修改**：**v2/src 零修改**（纯验收）；v2/README.md runbook 事实（NapCat 重定向启动、M2 启用步骤）；Memory §9M；.ai-handoff/ 6 文件
- **REAL ENV**：**VERIFIED**——真实群消息 → Task（deadline `2026-08-14 15:59 UTC` 精确）；structured_mode=json_fallback（DeepSeek）；普通聊天 skipped 无泄漏；语义重复不创建第二 Task；重启 DB 持久化 + NapCat 自动重连；M1 hello 共存（retcode 0）
- **测试**：316 passed 保持；package isolation PASS；Anti-AstrBot PASS
- **审核状态**：M2b.2 = REAL_ENV_ACCEPTANCE_COMPLETE AWAITING_EXTERNAL_M2_FINAL_REVIEW；M2 FINAL = NOT PASS；M3 NOT_AUTHORIZED

## 2026-08-10 · M2 FINAL CONTINUITY CLEANUP

- **任务**：外部 M2b.2 技术审核 PASS 后的纯文档连续性修复（M2 FINAL 暂 CHANGES_REQUESTED 因 stale 状态）
- **Commit**：docs: finalize M2 continuity state（本轮）
- **主要修改**：
  - AGENT_MEMORY：Section 2/3/18 语义扫描修复（M2b.1 PASS / M2b.2 REAL_ENV PASS / M2 TECHNICALLY_COMPLETE / M3 NOT_AUTHORIZED）；代码状态表中性化
  - README：能力现状 Implemented/Not-yet 双区、架构双路径（Echo + TaskPipeline）、依赖以 pyproject 为准、NapCat EPIPE 本机观察措辞
  - pyproject：仅 description milestone-neutral（version/deps/packages/build 未动）
  - CHATGPT_MEMORY §9N：CONTINUITY_CORRECTION / DOCUMENTATION_RULE ×2
- **测试**：**未重跑**（零生产源码修改）；316 passed 为 M2b.2 历史证据
- **审核状态**：M2 = AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW；M2 FINAL = NOT YET DECLARED；M3 NOT_AUTHORIZED

## 2026-08-12 · M3 REMINDER

- **任务**：M3 Reminder 里程碑（DB facts + ReminderService + APScheduler + TaskService 联动 + schema v2 + 本地真实调度器验收）
- **Commit**：feat: implement M3 reminder lifecycle（本轮）
- **主要修改**：schema v1→v2（reminders 表，owned migration 零变更拒绝）；Reminder enums/ORM/Repository；reminder_policy（三档/quiet-hours/去重/60s）；ReminderService（幂等 plan/cancel/resync/fire）；ReminderScheduler（APScheduler 3.11，确定性 job_id，remove-then-add，SchedulerNotRunningError 容错）；TaskService 生命周期联动（可选注入）；runtime 接线（CAMPUSCUE_REMINDERS=1）；config ReminderConfig；pyproject +apscheduler
- **测试**：新增 28 → **344 passed**；本地真实调度器验收 PASS（facts/jobs 一致性、重启 resync、deadline 变更、complete 取消、0 投递）；package isolation PASS（apscheduler 3.11.3）；Anti-AstrBot PASS
- **REAL ENV**：M3 无 QQ/NapCat（LOCAL REAL SCHEDULER）；M2b.2 REAL ENV 保留
- **审核状态**：M3 = IMPLEMENTATION_COMPLETE AWAITING_EXTERNAL_REVIEW；M3 FINAL NOT YET DECLARED；M4 NOT_AUTHORIZED


## 2026-08-12 · M3.1 REMINDER HARDENING

- **任务**：外部 M3 复核 PASS_WITH_FIXES 的 6 项硬化修复（A-F）
- **Commit**：fix: harden M3 reminder invariants（本轮）
- **主要修改**：runtime ReminderPolicy 接线（config 真消费，去重复真值）；quiet-hours 不超 deadline 硬不变量（clamp/discard）；resync_all 先 clear_all 真重建；v1 迁移前 schema 验证（表/列/单行版本，零变更拒绝）+ 迁移 SQL CHECK 约束与 fresh 对齐；ReminderService 默认 NoopDelivery
- **测试**：新增 10 → **354 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无 QQ（M3 本地调度器）；M2b.2 REAL ENV 保留
- **审核状态**：M3 = HARDENING_COMPLETE AWAITING_EXTERNAL_REVIEW；M3 FINAL NOT YET DECLARED；M4 NOT_AUTHORIZED


## 2026-08-12 · M3.2 FINAL GATE FIX

- **任务**：外部 M3.1 复核 PASS；M3 FINAL CHANGES_REQUESTED——3 项窄修复（A/B/C）
- **Commit**：fix: close M3 final reminder edge cases（本轮）
- **主要修改**：quiet-hours canonical is_inside_quiet_hours 谓词 + clamp 改 quiet_start 前（22:59:59）+ overnight-only 契约 fail-fast；_precheck 全局恰一行（版本分发前）；composition-root spy 接线测试
- **测试**：新增 9 → **363 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无 QQ（M3 本地调度器）；M2b.2 REAL ENV 保留
- **审核状态**：M3 = FINAL_FIX_COMPLETE AWAITING_EXTERNAL_REVIEW；M3 FINAL NOT YET DECLARED；M4 NOT_AUTHORIZED


## 2026-08-12 · M3.3 FINAL RECOVERY FIX

- **任务**：外部 M3.2 复核 PASS；M3 FINAL CHANGES_REQUESTED——resync 对账缺口（A）+ 当前版本结构验证（B）+ 17_MILESTONES（C）
- **Commit**：fix: complete M3 reminder recovery semantics（本轮）
- **主要修改**：resync_all 真业务对账（Tasks→facts→jobs；保留匹配 fact 身份/创建缺失/取消 stale/不补发/幂等无 churn）；TaskRepository.list_pending_with_deadline（不截断）；v1/v2 共享 _validate_application_schema（create_all 前只读验证，零变更拒绝）；17_MILESTONES gate 修复
- **测试**：新增 7 → **370 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无 QQ（M3 本地调度器）；M2b.2 REAL ENV 保留
- **审核状态**：M3 = FINAL_RECOVERY_FIX_COMPLETE AWAITING_EXTERNAL_REVIEW；M3 FINAL NOT YET DECLARED；M4 NOT_AUTHORIZED


## 2026-08-12 · M3.4 STORAGE SAFETY FINAL SEAL

- **任务**：外部 M3.3 复核 PASS；M3 FINAL CHANGES_REQUESTED——2 个存储安全 blocker（原子迁移 / 完整列验证）
- **Commit**：fix: seal M3 database migration safety（本轮）
- **主要修改**：v1→v2 迁移单显式事务（BEGIN IMMEDIATE + 逐条 execute + COMMIT/ROLLBACK，弃 executescript）；schema_meta=1 + reminders（半迁移）→ 拒绝零变更；v1/v2 完整 ORM 列契约 manifest（非子集：tasks 15 列/reminders 10 列/provider_configs 13 列）
- **测试**：新增 8 → **378 passed**；package isolation PASS；Anti-AstrBot PASS
- **REAL ENV**：无 QQ（M3 本地调度器）；M2b.2 REAL ENV 保留
- **审核状态**：M3 = STORAGE_SAFETY_FINAL_SEAL_COMPLETE AWAITING_EXTERNAL_REVIEW；M3 FINAL NOT YET DECLARED；M4 NOT_AUTHORIZED


## 2026-08-17 · M4 AGENT TOOL LOOP CHECKPOINT

- **任务**：提交 M4 Agent implementation + peer-review hardening，停止继续开发，等待 External ChatGPT 独立审核。
- **Commit**：（本 checkpoint）
- **主要修改**：Provider-neutral Tool Calling、ToolRegistry、trusted source-scoped Task Tools、CampusAgentRuntime bounded loop、explicit routing、per-thread lock、LRU thread cap、CJK ContextBudget、event-timestamp prompt、configuration/package wiring、peer-review regression tests。
- **Workspace Agent local verification**：full V2 **453 passed**；M4 Provider/Agent/Router focused **44 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS。These are not independent External ChatGPT results。
- **Real environment**：Real Provider Tool Call **NOT RUN**；Real QQ Agent E2E **NOT RUN**；QQ processes/protected primary account **NOT TOUCHED**。
- **Known limitation / out of scope**：M3 Task/Reminder cross-repository atomicity remains an open design risk; startup `resync_all()` recovery is accepted。No unit-of-work or Reminder architecture redesign in this checkpoint。
- **Gate**：M3 FINAL = PASS；M4 = IMPLEMENTATION_COMPLETE_REAL_ENV_PENDING；M4 FINAL = NOT YET DECLARED；M5 = NOT_AUTHORIZED。

## 2026-08-18 · M4.1 STATIC HARDENING + FRESH PACKAGE ISOLATION

- **任务**：M4.1 静态加固 + 全新安装包隔离验证（不跑 Real Provider / QQ / M5；不改业务逻辑，除非隔离暴露真实 packaging/import bug）。
- **Commit**：fix: harden M4 agent service boundaries（本 checkpoint）
- **主要修改**：
  - TaskService 公开 `DEADLINE_UNSET` sentinel（省略=不变 / 显式 None=清除 / naive 拒绝；替换内部 `_UNSET`）
  - handlers/agent.py：missing-source / disabled-source gate（安全本地回复，不触发 Agent、不拼接 LLM 结果）
  - Trusted provenance：AgentContext/ToolContext 新增 `user_text`（runtime 信任值）；`task_create.source_text_reference` 不再由模型注入
  - ContextBudget：当前用户输入只计一次（live turn 不再重复合成）
  - Provider timeout 独立性：Agent LLM 请求 `timeout_s=None`（不派生 tool 超时）
  - M4 第一版多创建限制契约化（M2 唯一约束，无 schema v3）
- **Workspace Agent local verification（FRESH installed-package isolation）**：[TEST_CONFIRMED] 全新隔离环境创建、working-tree V2 以真实安装包（non-editable）+ test extras 安装成功；imports resolved from fresh environment installed V2 package（campuscue.agents / campuscue.tools / jsonschema 均正确解析，无 Legacy/AstrBot/旧 venv/PYTHONPATH 泄漏）；M4.1 focused **88 passed**；full V2 **466 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS。These are not independent External ChatGPT results。
- **Real environment**：Real Provider Tool Call **NOT RUN**；Real QQ Agent E2E **NOT RUN**；QQ processes/protected primary account **NOT TOUCHED**。
- **Known limitation / out of scope**：[DESIGN_LIMITATION][M4] One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged；second `task_create` safely fails；no schema v3。M3 Task/Reminder cross-repository atomicity remains an open design risk; startup `resync_all()` recovery is accepted。
- **Gate**：M3 FINAL = PASS；M4 = STATIC_HARDENING_COMPLETE_REAL_ENV_PENDING；M4 FINAL = NOT YET DECLARED；M5 = NOT_AUTHORIZED。

## 2026-08-18 · M4.2 REAL PROVIDER TOOL CALL

- **任务**：真实 Provider M4 Tool Calling 验收（不碰 QQ/NapCat；不开始 M5；不改 M3；无 mock/硬编码）。
- **Commit**：fix: support real M4 provider tool call（本 checkpoint）
- **验收结果**：[TEST_CONFIRMED] **REAL PROVIDER TOOL CALL = PASS**——provider_type=openai_compatible，model=deepseek-chat，真实 httpx transport（api.deepseek.com；secret_reference=CAMPUSCUE_LLM_API_KEY；secret 值不落盘）。真实 Provider 自主发出 `task_list`（scope=week/today，模型选择）→ ToolRegistry → TaskService → 临时真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → 最终回答反映合成 DB 任务；模型还自主追加 `task_get`。通过 TaskService 改 title 后第二次查询回答随之变化（数据驱动，非硬编码）；Source A/B 作用域隔离双向验证通过。
- **暴露并修复的真实兼容性 bug（最小聚焦修复）**：真实 DeepSeek 在 tool-call 轮次同时返回辅助 content 文本 + tool_calls，原 `_parse_ok` 硬判 `MALFORMED_OUTPUT`（M4 §8 双形状设计未覆盖真实端点行为）。修复：tool_calls 权威、辅助文本丢弃（Agent loop 保持 final-text / tool-call 两种明确形状）；`test_6b_mixed_content_and_tool_calls_keeps_tool_calls` 覆盖新契约；docs/v2/08 补充真实兼容说明。
- **回归（修复后）**：[TEST_CONFIRMED] 新建 fresh installed-package 环境 `.venv-m42fresh`（源码变更后按要求重做隔离）；M4 focused **88 passed**；full V2 **466 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret/PII scan PASS；imports resolved from fresh environment installed V2 package。These are not independent External ChatGPT results。
- **Real environment**：Real Provider Tool Call **PASS（2026-08-18）**；Real QQ Agent E2E **NOT RUN（下一门，本 checkpoint 未授权）**；QQ processes/protected primary account **NOT TOUCHED**。
- **Known limitation / out of scope**：[DESIGN_LIMITATION][M4] One source message can create at most one Task in the first version（M2 `(source_id, source_message_id)` 唯一约束不变；无 schema v3）。M3 Task/Reminder cross-repository atomicity remains open design risk; startup `resync_all()` recovery accepted。
- **Gate**：M3 FINAL = PASS；M4.1 STATIC HARDENING = PASS；M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING；M4 FINAL = NOT YET DECLARED；M5 = NOT_AUTHORIZED。

## 2026-08-19 · M4.3 REAL QQ AGENT E2E

- **任务**：真实 QQ Agent E2E 验收（M4 最后真实环境 Gate）；先重建独立 NapCat 测试环境，再完成真实 QQ → Agent Tool Loop → SQLite → QQ 回复闭环。
- **Commit**：（本 checkpoint）
- **主要修改**：**v2/src 零修改**（纯验收 + 文档）；.ai-handoff/ 6 文件；docs/context 双 Memory；docs/v2/17_MILESTONES（gate 更新）；docs/v2/08（M4 激活状态更新）。
- **NapCat 环境**：官方 NapCat.Shell.Windows.Node v4.18.19（GitHub NapNeko/NapCatQQ Release，SHA256 校验）；目录 `C:\Tools\NapCat\m43-clean`；补齐 `crypto.dll`/`ssl.dll`；`NAPCAT_DISABLE_MULTI_PROCESS=1` 避免 worker `--no-sandbox` bad-option；TEST_BOT 登录（quick login 需手Q 验证 → 二维码人工扫码）。
- **REAL ENV**：**VERIFIED**——真实 QQ `@TEST_BOT 我这周有什么事情？` → Reverse WS → CampusCue → 真实 DeepSeek `task_list` → TaskService → SQLite → 第二次 Provider 调用 → `send_group_msg` retcode 0 回复任务列表；生产 TaskService 改任务标题后第二次回答随数据变化；普通不 @ 消息不触发 Agent（仅 M2 extraction skipped）。
- **测试**：M4 focused **88 passed**；full V2 **466 passed**（M4.2 fresh `.venv-m42fresh` 历史证据）；git diff --check PASS；Secret/PII scan PASS。
- **Gate**：M3 FINAL = PASS；M4.1 STATIC HARDENING = PASS；M4.2 REAL PROVIDER TOOL CALL = PASS；M4.3 REAL QQ AGENT E2E = PASS；M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW；M4 FINAL = NOT YET DECLARED；M5 = NOT_AUTHORIZED。

## 2026-08-19 · M5 API + REALTIME

- **任务**：完整实现 M5 FastAPI REST + SSE；schema v3；Backup/Restore/Import/Export；Auth；Runtime API lifecycle。
- **Commit**：feat: implement M5 API and realtime（本 checkpoint）
- **主要修改**：
  - 新增 `campuscue/api/`（app/dependencies/auth/errors/schemas/realtime/routes/*）+ `core/realtime.py` + services（provider/settings/system）
  - TaskService/ReminderService/TaskPipeline 增加 optional RealtimeNotifier
  - Runtime 增加 ApiConfig + API server lifecycle；`CAMPUSCUE_API=1` 启用，默认 127.0.0.1:6200
  - Schema v3：settings 表、sources.deleted_at 软删除、M5 indexes；v1→v2→v3 atomic migration
  - pyproject 增加 fastapi/uvicorn/pydantic，packages 含 campuscue.api
- **测试**：新增 M5 14 tests；full V2 **480 passed**（fresh `.venv-m5fresh` non-editable）；compileall PASS；Anti-AstrBot PASS；uvicorn local HTTP smoke PASS。
- **Gate**：M4 FINAL = PASS；M5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M5 FINAL = NOT YET DECLARED；M6 = NOT_AUTHORIZED。

## 2026-08-20 · M5.1 FINAL HARDENING

- **任务**：修复 External ChatGPT 对 M5 commit `2d34d3382c7c7770536918926b45d1ba1bfc10e4` 的 A-E 审查问题；不进入 M6。
- **主要修改**：SSE subscriber 显式 close 状态/唤醒 active stream；`ApiConfig.sse_heartbeat_interval` 接线；Uvicorn `server.started` readiness barrier + bounded timeout + occupied-port rollback；删除重复 `/api/v1/system/health`；OneBotAdapter optional neutral connection callback 发布 `connection.updated`；Task/Reminder/Pipeline 在业务 commit 后隔离 realtime publish failure。
- **测试**：M5/M5.1 focused **23 passed**；本轮新增 **7 passed**；fresh `.venv-m51fresh` non-editable full V2 **487 passed**；compileall PASS；Anti-AstrBot PASS；local HTTP/SSE readiness and occupied-port rollback PASS；git diff --check PASS。
- **Gate**：M4 FINAL = PASS；**M5.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；M5 FINAL = NOT YET DECLARED；M6 = NOT_AUTHORIZED。

## 2026-08-20 · M5.1.1 FINAL SSE ROUTE CLEANUP

- **任务**：修复 External ChatGPT 发现的 early HTTP SSE disconnect lifecycle edge case。
- **主要修改**：`/api/v1/stream` 外层 generator 增加 `finally` cleanup；客户端在 `: connected` 后立即关闭时也会调用幂等 `hub.unsubscribe()`。
- **测试**：新增真实 route-level body-iterator lifecycle regression **1 passed**；focused **24 passed**；fresh `.venv-m511fresh` non-editable full V2 **488 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；secret/PII scan PASS。
- **Gate**：M4 FINAL = PASS；M5.1.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M5 FINAL = NOT YET DECLARED；M6 = NOT_AUTHORIZED。

## 2026-08-20 · M6 WEBUI IMPLEMENTATION CHECKPOINT

- **任务**：按 M6 授权直接实现 `v2/web/`，保持 M5 backend frozen；完成首页、任务、消息、日历、AI 助手、连接、模型提供商、设置八个区域。
- **实现**：Vue 3 + TypeScript + Vite + Vue Router + Pinia + Lucide；M5 REST canonical integration；SSE notification-only reconnect/backoff；optimistic task completion rollback；light/dark tokens；responsive sidebar/bottom navigation；no emoji or secrets in UI fixtures。
- **测试**：typecheck PASS；production build PASS；Vitest 2 passed；Playwright 9 passed；axe violations 0；screenshots at 390/599/768/1024/1440；backend baseline remains 488 passed from fresh installed package。
- **Gate**：M5 FINAL = PASS；**M6 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。

## 2026-08-20 · M6.1 WEBUI INTEGRATION HARDENING

- **触发**：External review 将 M6 标记为 `CHANGES_REQUESTED`，指出 task status、命名 SSE、Settings/System 接线、硬编码 Calendar、mock-only integration 及多个页面 CRUD/筛选缺口。
- **修复**：统一 canonical `done` 状态；fetch + Bearer SSE reader 消费命名事件并 REST refresh；补齐真实 Settings/System、Tasks CRUD/filter/editor/delete/deadline clear、Calendar、Messages detail/filter、Connections、Providers、Agent source selector。
- **真实验收**：隔离 SQLite + 真实 M5 FastAPI composition + RealtimeHub + deterministic local fake provider upstream；真实 task mutation → named SSE → REST refresh、CRUD、calendar、source/provider test、settings/export 均通过。
- **测试**：typecheck PASS；production build PASS；Vitest 2 passed；Playwright full **12 passed**；axe violations 0；页面截图位于 `.ai-handoff/visual/m61/`；backend fresh installed-package baseline **488 passed**。
- **Gate**：M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；**M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。

## 2026-08-20 · M6.2 SUBTLE VISUAL POLISH

- **基线**：创建并推送 annotated tag `m6.1-ui-baseline`，指向 M6.1 stable UI commit；`.ai-handoff/visual/m61/` 保持未覆盖。
- **范围**：保留 IA、layout、API、store、router、backend、schema 和业务流程；只通过 tokens/shared CSS 与少量 presentation markup 增加 surface hierarchy、teal accent、status/deadline/category detail、Home/Tasks/Agent polish、全站 micro-interactions 和 dark/mobile refinement。
- **约束**：无大面积渐变、紫色 AI 风、neon、glassmorphism、emoji、robot、装饰插画或 Product Rewrite。
- **验收**：typecheck PASS；production build PASS；Vitest 2 passed；Playwright full **12 passed**（shared real harness 固定单 worker）；axe violations 0；real integration PASS；light screenshots `.ai-handoff/visual/m62/`；dark evidence `.ai-handoff/visual/m62-dark/`。
- **Gate**：M5 FINAL = PASS；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。

## 2026-08-20 · M6.2.1 FINAL PRODUCT DETAIL CLEANUP

- **任务**：在 M6.2 visual language 上完成最终产品细节收口；不重构 IA、不修改 M5 backend、不进入 M6 FINAL 或 M7。
- **实现**：Home 使用 Settings timezone 的动态日期/星期和本周 pending 计数；upcoming 按 deadline 排序；完成与忽略动作分离；移动端底栏改为总览/任务/日历/AI/更多，并提供可访问 More bottom sheet；移除 priority `urgent`、加入共享中文 task label helper、修正主题切换 icon/label、移除 topbar 假头像。
- **测试**：typecheck PASS；Vitest **4 passed**；M6 focused Playwright **12 passed**；axe violations 0；light/dark screenshots 分别写入 `.ai-handoff/visual/m621/`、`.ai-handoff/visual/m621-dark/`；m61/m62/m62-dark evidence 保持未覆盖。
- **Gate**：M5 FINAL = PASS；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。

## 2026-08-20 · M6.3 VISUAL CHARACTER PASS

- **基线**：创建并推送 annotated tag `m6.2.1-ui-baseline`，指向 `01461b9e4a9ece79ee0ed01343277f71ea803aef`；m61/m62/m621 evidence 未覆盖。
- **范围**：保持 Blue + Teal、IA、M5 contract、store、router、backend、schema 和业务逻辑；引入 Cue Line + Cue Dot motif、section tint、page identity、structured empty state、Tasks/Agent/Calendar/Home 核心页节奏，以及 Messages/Connections/Providers/Settings 的统一细节。
- **约束**：无渐变、玻璃拟态、neon、紫色 AI 风、插画、emoji、新图片或 Admin Template 式填空；Mobile Agent composer 调整到 bottom nav 之上。
- **验收**：typecheck/build PASS；Vitest **4 passed**；focused Playwright **12 passed**；axe 0；real integration 两条测试 individually PASS；light/dark screenshot capture PASS；证据位于 `.ai-handoff/visual/m63/`、`.ai-handoff/visual/m63-dark/`。
- **Gate**：M5 FINAL = PASS；M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW；**M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。

## 2026-08-20 · M6.4 INFORMATION LAYERING PASS

- **基线**：创建并推送 annotated tag `m6.3-ui-baseline`，指向 `5152bc6b5008e8c6fdf2cf28ff8040d87e416699`；旧 evidence 未覆盖。
- **实现**：以 progressive disclosure 重排 Tasks、Agent、Messages 的一级/二级/高级信息；加入 Tasks filter sheet/More/context aside、Agent context rail/mobile sheet/four prompts、Messages desktop master-detail/mobile detail、Calendar selected-day agenda/dot cap；Connections/Providers/Settings 收纳高级信息；移除用户界面的工程化文案；夹具统一为 5 tasks / 3 messages / 3 sources / 1 provider。
- **范围**：保持 M6.3 Blue + Teal、Cue Line + Cue Dot、light/dark、sidebar/mobile nav、Lucide、真实 REST/Agent API；不改 backend/API/store/router/schema/business logic。
- **验收**：fresh installed-package `.venv-m64fresh` full V2 **488 passed**；typecheck/build PASS；Vitest **4 passed**；focused Playwright **16 passed**；axe 0；real integration **2 passed**；light/dark screenshots 位于 `.ai-handoff/visual/m64/`、`.ai-handoff/visual/m64-dark/`；compileall/Anti-AstrBot/diff-check/secret-PII PASS。
- **Gate**：**M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## 2026-08-20 · M6.5 VISUAL DEPTH & PRODUCT COMPOSITION PASS

- **基线**：创建并推送 annotated tag `m6.4-ui-baseline`，指向 `26392e633b1ab47bfe39c1831c774c638f9b7076`；m63/m64 evidence 保持不覆盖。
- **实现**：完成 differentiated page widths、editorial grid composition、canvas/section/primary/raised surface hierarchy、typography scale、stronger brand area、light/dark responsive refinement；局部加入玻璃拟态材质。
- **玻璃拟态边界**：仅用于 Agent canvas/context/composer、Home focus、连接状态、inspector/diagnostics/dialog；任务正文、消息列表和设置表单保持实色或 tint；`backdrop-filter` 有 `@supports` 实色回退。
- **验收**：typecheck/build PASS；Vitest 4；focused Playwright 16；axe 0；real integration 2；light/dark m65 screenshot capture PASS；prior evidence preserved。
- **Gate**：**M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## 2026-08-20 · M6.5.1 REAL GLASSMORPHISM CORRECTION

- **Starting HEAD**：`524e4a13a2ba257fa5b04194219c17c9d6cd068c`；不 amend M6.5 旧提交。
- **范围**：只处理 Glass 核心四处 App Shell/Home/Tasks/Agent；Dark 与 Neumorphism 冻结；M6.4 Information Layering、demo dataset、IA 和业务逻辑保持不变。
- **实现**：连续 Atmospheric Canvas；`glass-subtle/panel/raised/floating` 分级材质；Backdrop/Tint/Blur/Edge Light/Shadow；Text Contrast First；`@supports not (backdrop-filter)` 实色回退。
- **验证**：Glass material Playwright 1 passed；M6 focused Playwright 16 passed；typecheck/build PASS；axe 0；390/599/768/1024/1440 responsive PASS；专用 evidence 在 `.ai-handoff/visual/m651/glass/`。
- **Gate**：**M6.5.1 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**GLASS FINAL = NOT YET DECLARED**；**DARK REVIEW = PENDING**；**NEUMORPHISM REVIEW = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## 2026-08-20 · M6.5.2 GLASS REFINEMENT & PRODUCTIZATION

- **外部审核结论**：M6.5.1 Glass direction = PASS；材质已可感知。本轮仅做 refinement，不放大玻璃效果，不进入 Dark/Neumorphism 或 Stage 2。
- **实现**：降低 Atmospheric Canvas 强度（尤其 warm amber）；建立 Base / Primary / Context / Raised / Floating semantic tiers 与统一 blur/elevation tokens；Home Today 去除嵌套白色 empty card；Tasks toolbar/context/rows 统一并修复 raw ISO date；Agent Context Rail、顶部 utility controls、prompt chips、composer 和 mobile separation 收口；Settings backup preview 使用共享本地化日期 formatter。
- **证据**：Stage 1 新证据 `.ai-handoff/visual/m652/glass/` 五张；M6.5.1 `.ai-handoff/visual/m651/glass/` 从 `m6.5.1-glass-baseline` 恢复，旧 evidence 未覆盖。
- **验收**：typecheck/build PASS；Vitest 4；M6.5.2 focused 2；M6 focused 16；M6.5.1 regression 1；real integration 2；fresh installed-package full V2 488；compileall/Anti-AstrBot/diff-check/Secret+PII PASS；axe 0；responsive overflow、console error、theme persistence、fallback PASS。
- **Gate**：**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；**GLASS FINAL = NOT YET DECLARED**；**DARK REVIEW = PENDING**；**NEUMORPHISM REVIEW = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## 2026-08-21 · M6.5.3 DARK UI STAGE 1

- **基线**：创建并推送 annotated tag `m6.5.2-glass-baseline`，保护 M6.5.2 Glass commit `63d7aeb4177b61bc73bffa336d6743e50c780559`；不 amend Glass commit。
- **实现**：新增独立 Dark solid-surface productivity language 与 dark tokens；完成 App Shell、Home、Tasks、Agent、Settings Theme Selector；保留 Glass 视觉与内部 `light/dark` 兼容值，不改 API/schema/backend。
- **证据**：`.ai-handoff/visual/m653/dark/` 七张 Stage 1 screenshots；新增 Dark route-level Playwright regression。
- **验收**：Dark focused 2 passed；M6 focused 16；M6.5.2 Glass focused 2；real integration 2；typecheck/build/Vitest/Axe/overflow/console/theme persistence/Glass fallback/mobile composer safety PASS。
- **Gate**：**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**DARK FINAL = NOT YET DECLARED**；**NEUMORPHISM = PENDING**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。

## 2026-08-21 · M6.5.3 DARK UI STAGE 2

- **基线**：创建并推送 annotated tag `m6.5.3-dark-stage1-baseline`，保护 Stage 1 commit `5572811843d3bf5fb3bab5fc6d81f1955ffac7ce`；Glass baseline `m6.5.2-glass-baseline` 保持不变。
- **实现**：Dark solid language 扩展至 Calendar、Messages、Connections、Providers、Settings、Dialog、Bottom Sheet、Toast、Empty/Loading/Offline/Reconnecting；补齐连续 Calendar grid、Messages master-detail/sheet、低频 action hierarchy 与 1440/1024/390 responsive 状态。
- **主题语义**：移除 Theme Selector 的 nth-child CSS 文本伪装，使用真实 `跟随系统 / 玻璃拟态 / 深色界面` 标签；保留后端 `system/light/dark` contract；`system` 通过 `prefers-color-scheme` 解析并监听变化。
- **证据**：`.ai-handoff/visual/m653-stage2/dark/` 与 `.ai-handoff/visual/m653-stage2/compare/`，不覆盖 `.ai-handoff/visual/m653/dark/`。
- **验收**：Stage 2 Playwright 4；Stage 1 Dark 2；M6 16；Glass 2；real M5 integration 2；WebUI typecheck/build/Vitest；fresh installed-package V2 488；compileall/Anti-AstrBot/diff-check/secret+PII/axe/overflow/console/system-theme PASS。
- **Gate**：**M6.5.3 DARK STAGE 1 = PASS**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**DARK FINAL = NOT YET DECLARED**；**NEUMORPHISM = NOT_AUTHORIZED**；**M6 FINAL = NOT YET DECLARED**；**M7 = NOT_AUTHORIZED**。
- **2026-08-21 · M6.5.4 Neumorphism**：新增前端 `data-visual-theme` 材质架构，与后端 `data-theme` 的 `system/light/dark` contract 分离；完成 controlled same-material Neu canvas、定向双阴影、raised/inset hierarchy、平坦高频内容层、Settings 风格选择器及 1440/1024/390 evidence。验证：Neu focused 4 passed；Dark Stage 2 4、Dark Stage 1 2、M6 16、Glass 2、real integration 2；typecheck/build/Vitest；fresh installed-package V2 488；compileall/Anti-AstrBot/diff-check/secret+PII/axe/overflow/console/system-theme PASS。Gate：M6.5.4 NEUMORPHISM = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW；NEUMORPHISM FINAL/GLASS FINAL/DARK FINAL/M6 FINAL NOT YET DECLARED；M7 NOT_AUTHORIZED。
- **2026-08-21 · M6.5.4.1 Theme UX Cleanup**：External review 通过 Neumorphism material implementation；本轮删除用户可见的独立明暗模式入口，收敛为 `system | glass | dark | neumorphism` 单一视觉风格选择。System 根据 OS light/dark 解析为 Glass/Dark；显式 Glass/Dark/Neu 不受 OS 变化影响；backend payload 仍严格映射为 `system/light/dark`，永不发送 `neumorphism`。证据 `.ai-handoff/visual/m6541/`；focused 2 passed；M6 16；Glass 2；Dark 6；Neu 4；real integration 2；typecheck/build/Vitest/Axe/overflow/console/diff-check/secret+PII PASS。Gate：`M6.5.4.1 THEME UX = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`；`NEUMORPHISM MATERIAL = PASS`；所有 Final 与 M7 均未声明/未授权。
- **2026-08-21 · M6 Final Closure Candidate**：删除 Settings 旧 Appearance section、`themeOptions`、`appearance-picker` 与隐藏兼容 CSS；新增最终三主题全路由/响应式/可访问性回归和 `.ai-handoff/visual/m6-final-candidate/` coherent evidence index。Candidate Playwright 1、M6/real integration 18、theme/material focused 14、typecheck/build/Vitest 4 均通过；1440/1024/768/390 overflow、System OS resolution、persistence、Axe（含 dialog 与 More sheet）、console/page errors、backend payload mapping PASS。为满足 Dark dialog description 的 WCAG serious 对比度边界，仅增加一条可读性覆盖；未改变材质、布局、API 或业务逻辑。Gate：`M6.5.4.1 THEME UX = PASS`；`GLASS/DARK/NEUMORPHISM FINAL = AWAITING_EXTERNAL_FINAL_REVIEW`；`M6 FINAL = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW`；`M7 = NOT_AUTHORIZED`。
- **2026-08-21 · [M6_FINAL] External Visual Review PASS**：对 `.ai-handoff/visual/m6-final-candidate/` 完成代码事实、视觉证据、信息架构、三主题一致性、Theme Architecture、Regression、Responsive 与 Accessibility 审核。Glass、Dark、Neumorphism、Theme switching、Theme persistence、Backend contract、Responsive、Accessibility、Regression 全部 PASS。CampusCue WebUI completed；supported visual styles：Glassmorphism、Dark UI、Neumorphism。M7 = NOT_AUTHORIZED。
- **2026-08-22 · M7 Roadmap Design**：仅完成 M7 产品规划与技术路线设计，新增 `docs/v2/M7_ROADMAP.md`。推荐范围收敛为首次接入五分钟闭环、可信任务跟进、受边界约束的 Agent copilot 与可重复 Demo；Campus Data Integration、Collaboration、durable memory 与通用 Agent 明确延期。M7 implementation 未开始，当前 Gate：`M7 ROADMAP = ROADMAP_DESIGN_COMPLETE_AWAITING_EXTERNAL_REVIEW`；`M7 IMPLEMENTATION = NOT_AUTHORIZED`。
- **2026-08-22 · M7.1 First-use Activation**：复用现有 `pending_confirm`、Connection Test、TaskPipeline、provenance 与 source-scoped Agent tools；新增 Home 轻量启动引导、Connections 安全失败/禁用提示、Task/Message trust summary、Agent 连接入口，以及 deterministic provider + real pipeline harness。官方 fixture 的显式日期+时间现解析为 `2026-08-28T14:00:00Z`。M7-A01～A07 与 fake reminder boundary tests 通过；fresh installed-package V2 **496 passed**；WebUI typecheck/build/Vitest/Playwright/M6 三主题回归通过；无 API/Schema 变更、无真实 QQ/NapCat、runtime 仍 `NoopDelivery`。Gate：`M7.0 PRODUCT CONTRACT = PASS`；`M7.1 FIRST-USE ACTIVATION = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`；`M7.2/M7.3 = NOT_AUTHORIZED`。
- **2026-08-22 · M7.1 External Review + M7.2 OneBot Reminder Delivery**：M7.1 external source review = `PASS`。补齐真实 source connection-test disconnected coverage，ActivationGuide 的 Agent step 改由 `/agent/threads` canonical runtime state 推导。实现 M7.2 closed `noop|onebot` operator opt-in（默认 Noop）、enabled/non-deleted OneBot GROUP source-scoped delivery、deterministic privacy-safe reminder template、safe `delivery:*` error persistence、duplicate fire guard，以及 scheduler-before-delivery race / shutdown ordering 修复。Fake NapCat success/disconnected/action-failure、runtime opt-in、wrong-source/no-source/task-done 与 UI status evidence 已完成；Schema/API changes = NONE；automatic retry/additional channels = NOT_IMPLEMENTED_EXPECTED；REAL QQ E2E = NOT_RUN。Gate：`M7.1 = PASS`；`M7.2 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`；`M7.3 = NOT_AUTHORIZED`。
