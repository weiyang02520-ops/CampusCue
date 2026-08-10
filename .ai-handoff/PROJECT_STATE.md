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
- M2a = **PASS**（最终外部审核通过）
- **M2b.1 = FINAL_IMPLEMENTATION_COMPLETE**（AI-first PASS + M2b.1.1 hardening PASS + M2b.1.2 fallback/dedup 契约修正完成）— **AWAITING_EXTERNAL_FINAL_REVIEW**
- **M2b.2 = NOT_AUTHORIZED**（等 M2b.1 最终复核）
- M2 最终 = NOT PASS（等 M2b.2）
- status：**AWAITING_EXTERNAL_M2B1_FINAL_REVIEW**

## completed

- M0 / M0.1 / M0.2（PASS）
- M1 / M1.1 / M1.2 / M1.3（PASS）
- M2a / M2a.1 / M2a.2（PASS）
- **M2b.1 系列（FINAL_IMPLEMENTATION_COMPLETE）**：AI-first pipeline（ADR-013）+ M2b.1.1 Real-Gate Hardening（缺 secret fail-before-transport / provider-model 审计 / model_said_none reason / fallback 分类 / context resize / 显式年份 / test DB 隔离 / 所有权清理 / dedup key / injection 防御）+ **M2b.1.2 Fallback Contract Fix（generic unsupported 不 fallback / 单 canonical system 契约 / fallback 上下文保留 / whitespace secret / no-deadline 跨课程不 dedup）**

## in_progress

- 无（M2b.1.2 完成，checkpoint 后停止，等待外部最终复核）

## blocked

- **M2b.2 仅阻塞于 M2b.1 外部最终复核**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **316 tests passed**（M2b.1.2 新增 14）；package isolation PASS（fresh venv `.venv-m2iso` + tzdata）；Anti-AstrBot PASS
- REAL ENV VERIFIED（M1.2，2026-08-10，NapCat v4.18.18 + 真实 QQ）——**保留自 M1.2，非本轮新验证**
- 外部审核状态：**awaiting**（M2a PASS；M2b.1 AI-first 方向 PASS；M2b.1.1 hardening PASS；M2b.1.2 待最终复核）

## unverified / known unknowns

- 真实 Provider（如 Ark）json_schema 支持度与真实 token 成本（M2b.2 真实验收；若 primary 行为证明需要，M2b.2 可加极小 endpoint 能力映射）
- 无迁移框架；未来 schema 版本需人工迁移

## architecture_decisions

- ADR-001 ~ ADR-013（docs/v2/adr/，含 ADR-013 AI-First Extraction）

## next_gate

- 外部 ChatGPT M2b.1 最终源码复核（10 项审核点）→ PASS 则 **M2b.2 授权**（真实 Provider + 真实 NapCat/QQ + SQLite 验收）

## external_review_focus（M2b.1.2 复核点）

1. generic "unsupported" 不再触发 structured fallback（`unsupported_parameter`+temperature → INVALID_REQUEST 1 call）
2. 结构化特定证据仍触发恰一次 fallback（`unsupported_response_format`/`invalid_json_schema`/message 证据 → 2 calls）
3. fallback 保留 canonical AI-first 语义（校园事务定义/AI-first 判断/上下文补全/信号 hints）
4. fallback 保留 prompt-injection defense-in-depth 边界（roles system+user；attack 永不进 system；含"输入即数据"语义）
5. fallback 保留有界上下文/当前消息/信号/时间戳（user 消息与 primary 完全一致）
6. whitespace-only secret → CONFIG_ERROR + 0 transport
7. no-deadline 不同已知课程不 dedup；`build_dedup_key` 语义一致
8. AI-first 行为未变（ADR-013 CURRENT；无 LocalPrefilter 回归）
9. 无 M2b.2 实现（真实 Provider/QQ 未运行）
10. state/handoff/memory 一致
