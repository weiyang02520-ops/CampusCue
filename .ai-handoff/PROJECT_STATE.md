# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0 = **PASS**；M1 = **PASS**（含 REAL ENV）；M2a = **PASS**；**M2b.1 = PASS（最终）**；**M2b.2 = REAL_ENV PASS**
- **M2 = AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW**（技术实现 + REAL ENV 已通过；仅剩连续性文档复核）
- **M2 FINAL = NOT YET DECLARED**（等外部）；**M3 = NOT_AUTHORIZED**
- status：**AWAITING_EXTERNAL_M2_FINAL_CONTINUITY_REVIEW**

## completed

- M0 / M0.1 / M0.2（PASS）
- M1 / M1.1 / M1.2 / M1.3（PASS）
- M2a / M2a.1 / M2a.2（PASS）
- M2b.1 / M2b.1.1 / M2b.1.2（PASS）
- **M2b.2（REAL ENV PASS）**：真实 QQ 群消息 → NapCat → Reverse WS → AI-first pipeline → DeepSeek → SQLite 全链路；测试 A-E 全 PASS（hello 共存/明确任务 deadline 精确/普通聊天 skipped/语义重复/重启持久化 + 自动重连）
- **M2 Final Continuity Cleanup（本轮）**：AGENT_MEMORY/README/pyproject 描述 stale 状态修复（纯文档）

## in_progress

- 无（M2 技术完成；checkpoint 后停止，等待外部最终连续性复核）

## blocked

- **M3 仅阻塞于 M2 外部最终连续性复核**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **REAL ENV VERIFIED（M2b.2，2026-08-10）**：真实 QQ 群消息全链路；structured_mode=json_fallback（DeepSeek）；deadline `2026-08-14 15:59 UTC` 精确；duplicate 不创建第二 Task；重启 DB 持久化 + NapCat 自动重连
- 最新 Workspace Agent checkpoint：316 tests（2026-08-10，M2b.2 时）——本轮零源码修改未重跑
- 外部审核状态：**awaiting**（M2a/M2b.1/M2b.2 技术 PASS；M2 最终连续性复核待通过）

## unverified / known unknowns

- 无阻塞性未知；真实模型 course 提取依赖消息原文是否含课程名（REAL_MODEL_VARIANCE，非 bug）
- 无迁移框架；未来 schema 版本需人工迁移

## architecture_decisions

- ADR-001 ~ ADR-013（docs/v2/adr/，含 ADR-013 AI-First Extraction）

## next_gate

- 外部 ChatGPT M2 最终连续性复核 → PASS 则 **M2 FINAL PASS + M3（Reminder）授权**

## external_review_focus（M2 Final Continuity 复核点）

1. AGENT_MEMORY 全文件语义一致（无 stale 活动状态：M2b.1 PASS / M2b.2 PASS / M2 TECHNICALLY_COMPLETE / M3 NOT_AUTHORIZED）
2. README 能力现状 = Implemented（M1+M2）/ Not yet（Reminder/Agent/API/WebUI）无矛盾
3. README 架构双路径（Echo + TaskPipeline）
4. README 依赖以 pyproject.toml 为准（不手动断言）
5. pyproject description milestone-neutral
6. NapCat EPIPE 措辞 = 本机观察非普适规则
7. 用户大号保护事实保留（无真实 ID）
8. 生产源码零修改
