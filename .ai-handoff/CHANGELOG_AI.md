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
