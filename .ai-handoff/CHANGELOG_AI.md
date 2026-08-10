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
