# PROJECT_STATE.md

> 人工项目阶段事实源。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0 = **PASS**（最终外部审核通过）
- M1 = **PASS**（REAL ENV VERIFIED 2026-08-10 + 外部技术最终审核）
- M1.3 = **CONTINUITY_PRIVACY_FIX_COMPLETE**（本轮：PII 脱敏 + Memory Current Truth 修复 + README runbook + canonical HANDOFF）— AWAITING_EXTERNAL_REVIEW
- M2 = **READY_NOT_STARTED / NOT_AUTHORIZED**（等 M1.3 外部确认）
- status：**AWAITING_EXTERNAL_M1_3_REVIEW**

## completed

- M0/M0.1/M0.2：研究 + 审计 + 20 份设计文档 + 10 ADR + 双 Memory + 4 项一致性修复（全部 PASS）
- **M1：独立 QQ Runtime 完整实现**
  - v2/ 独立 implementation root（ADR-011），与 Legacy V1 物理隔离
  - CampusEvent / EventBus（有界队列 + 有界并发）/ Router / EchoHandler / OutgoingMessage
  - OneBotAdapter：Reverse WS SERVER + token 校验 + 帧分类 + echo correlation + generation 竞态保护 + transport dedup
  - Anti-AstrBot Gate（AST 扫描 + 依赖扫描 + 隔离 smoke）PASS
  - 65 tests 全绿（unit 49 + integration 16）
  - Package isolation PASS（fresh venv 安装 v2/ + import + smoke）
  - 日志脱敏 + CAMPUSCUE_DIAGNOSTIC 显式诊断模式
  - **M1.1 修复**（外部源码审核 8 项）：stale finally 竞态、outbound 进 handler 边界、pending semaphore backpressure、config fail-fast、WS path 校验、严格响应校验、诊断模式去假 claim、移除 raw_message

## in_progress

- 无（M1.3 完成）

## blocked

- M2 阻塞于 M1.3 外部确认

## verified

- STATIC/UNIT/INTEGRATION/PACKAGE ISOLATION VERIFIED（87 tests + fresh venv）
- REAL ENV VERIFIED：**VERIFIED**（NapCat v4.18.18 + 真实 QQ：私聊/群聊 hello→received:hello、非 hello 不回复、重启自动重连、token 握手）

## unverified / known unknowns

- 真实 NapCat token handshake：**已真实验证**（NapCat 带 token 连接成功）
- NapCat post-format：**array 已真实兼容**
- V1 `extract()` LLM 测试缺口（B13）、时区硬编码（B12）——M2 修

## architecture_decisions

- ADR-001~011（docs/v2/18_DECISIONS.md + adr/）；M1 新增 ADR-011（V2 代码隔离）

## next_gate

- 外部 ChatGPT M1.3 复核（读 GitHub HEAD）→ M2 授权

## external_review_focus（M1 审核点）

1. V2 是否真的与 Legacy/V1 隔离（fresh venv 证据）
2. 无任何 astrbot import / runtime dependency（Gate 证据）
3. CampusEvent 是否 OneBot-independent
4. Reverse WS server ownership / stale connection race / 帧分类 / echo correlation / disconnect fail-pending
5. queue / in-flight / pending actions 三处 bounded
6. transport dedup 只执行一次；self-message 阻断 echo loop
7. normal logs 脱敏；diagnostic 模式默认 OFF
8. 是否偷偷实现了 M2
