# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0 = **PASS**；M1 = **PASS**（含 M1.1 correctness + M1.2 REAL ENV + M1.3 隐私清理）
- M2a = **PASS**（最终外部审核通过）；**M2b.1 = PASS_WITH_FIXES → M2b.1.1（Real-Gate Hardening）完成 — AWAITING_EXTERNAL_FINAL_REVIEW**
- **M2b.2 = NOT_AUTHORIZED**（等 M2b.1.1 外部最终确认）
- M2 最终 = NOT PASS（等 M2b.2）
- status：**AWAITING_EXTERNAL_M2B1_FINAL_REVIEW**

## completed

- M0 / M0.1 / M0.2（PASS）
- M1 / M1.1 / M1.2 / M1.3（PASS）
- M2a / M2a.1 / M2a.2（PASS）
- **M2b.1（PASS_WITH_FIXES）+ M2b.1.1（Real-Gate Hardening，本轮）**：缺 secret env 在 transport 前 fail、Extraction 记录 provider/model、model_said_none 保留 confidence/reason、schema fallback 仅 STRUCTURED_OUTPUT_UNSUPPORTED、ContextCollector window resize、显式年份不 auto-roll、test DB 隔离 fail-fast、TaskService 所有权清理、dedup_key 单一 helper、prompt-injection 防御（defense-in-depth）

## in_progress

- 无（M2b.1.1 完成，checkpoint 后停止，等待外部最终复核）

## blocked

- **M2b.2 仅阻塞于 M2b.1.1 外部最终确认**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **302 tests passed**（M1 87 旧 + M2a 116 + M2b.1 61 + M2b.1.1 新增 38 相关断言）；package isolation PASS（fresh venv `.venv-m2iso` + tzdata）；Anti-AstrBot PASS
- REAL ENV VERIFIED（M1.2，2026-08-10，NapCat v4.18.18 + 真实 QQ）——**保留自 M1.2，非本轮新验证**
- 外部审核状态：**awaiting**（M2a 已 PASS；M2b.1 AI-first 方向已 PASS；本轮 M2b.1.1 待最终复核）

## unverified / known unknowns

- 真实 Provider（如 Ark）json_schema 支持度与真实 token 成本（M2b.2 真实验收）
- 无迁移框架；未来 schema 版本需人工迁移

## architecture_decisions

- ADR-001 ~ ADR-013（docs/v2/adr/，含 ADR-013 AI-First Extraction）

## next_gate

- 外部 ChatGPT M2b.1.1 最终源码复核 → PASS 则 **M2b.2 授权**（真实 Provider + 真实 NapCat/QQ + SQLite 验收）

## external_review_focus（M2b.1.1 复核点）

1. Missing-secret fail-before-transport（配置了 secret_reference 但 env 缺失/空 → 本地 CONFIG_ERROR，0 transport calls）
2. Extraction 审计记录 provider/model（BaseProvider.model 公共属性；业务不碰 `_model`）
3. model_said_none 审计保留 confidence/reason（无虚构 Task；不持久化完整输入 context）
4. schema fallback 仅 STRUCTURED_OUTPUT_UNSUPPORTED（generic INVALID_REQUEST / AUTH / TIMEOUT 不 fallback）
5. ContextCollector context_window resize（窗口从 1 → 3 后缓冲区可增长）
6. 显式年份的过去日期拒绝而非 auto-roll（"2026年8月5日" 不变成 2027）
7. CAMPUSCUE_ENV=test + pipeline + 无 CAMPUSCUE_DB_PATH → 启动前 fail；confidence_threshold ∈ [0,1] 且 timezone 可解析
8. TaskService 单一状态所有权（pipeline 决策，TaskService 应用）；无死 decide_pending_confirm / 无 pipeline 私有访问
9. dedup_key 单一 canonical helper（normalized title + course + deadline minute）
10. prompt-injection defense-in-depth（消息文本永不进 system role；固定 system prompt + schema）
