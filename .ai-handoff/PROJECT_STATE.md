# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0-M2 全部 **FINAL PASS**（含 M2b.2 REAL ENV；M2 FINAL PASS @ 23083cb）
- **M3 = HARDENING_COMPLETE AWAITING_EXTERNAL_REVIEW**（M3 实现 + M3.1 修复轮：config 接线/post-deadline 禁/resync 真重建/迁移验证/约束对齐/默认投递）
- **M3 FINAL = NOT YET DECLARED**（等外部）；**M4+ = NOT_AUTHORIZED**
- status：**AWAITING_EXTERNAL_M3_FINAL_REVIEW**

## completed

- M0 / M0.1 / M0.2（PASS）；M1 / M1.1 / M1.2 / M1.3（PASS）；M2a / M2a.1 / M2a.2 / M2b.1 / M2b.1.1 / M2b.1.2（PASS）；M2b.2（REAL ENV PASS）
- **M3 Reminder（M3 + M3.1）**：DB reminder facts（canonical）+ ReminderService（幂等 plan/cancel/resync/fire）+ APScheduler 3.11（确定性 job_id）+ TaskService 联动 + schema v1→v2 迁移 + 本地真实调度器验收；**M3.1 硬化**：ReminderPolicy runtime 接线、quiet-hours 不超 deadline、resync 先 clear 真重建、迁移前 schema 验证 + CHECK 约束对齐、默认 NoopDelivery

## in_progress

- 无（M3 实现完成，checkpoint 后停止，等待外部复核）

## blocked

- **M4+ 仅阻塞于 M3 外部复核**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **354 tests passed**（+28 M3 + 10 M3.1）；package isolation PASS（fresh venv `.venv-m2iso` + apscheduler 3.11.3）；Anti-AstrBot PASS
- **LOCAL REAL SCHEDULER VERIFIED（M3，2026-08-12）**：真实 APScheduler 3.11（非 mock）——facts/jobs 一致性、重启 resync、deadline 变更、complete 取消、无投递
- REAL ENV（M2b.2，2026-08-10）保留；M3 无 QQ 验收（不需要）
- 外部审核状态：**awaiting**（M0-M2 PASS；M3 待复核）

## unverified / known unknowns

- 真实端用户投递 UX（M3 仅 delivery 注入边界 + NoopDelivery；QQ/桌面通知为后续里程碑）
- 无迁移框架（v1→v2 owned migration；未来版本需人工扩迁移链）

## architecture_decisions

- ADR-001 ~ ADR-013（docs/v2/adr/）；M3 决策见 CHATGPT_MEMORY §9O

## next_gate

- 外部 ChatGPT M3 源码复核 → PASS 则 **M3 FINAL PASS + M4（Agent）授权**

## external_review_focus（M3 复核点）

1. schema v1→v2 迁移安全（保留数据/零变更拒绝/幂等重开）
2. DB reminder fact vs scheduler derived job 不变式
3. ReminderService 幂等（重复 plan 无重复 facts/jobs）
4. TaskService 生命周期联动（deadline/complete/dismiss/delete 取消）
5. resync 重建无重复；停机错过不补发
6. Clock/timezone 注入（无隐藏墙钟；DST 边界测试）
7. APScheduler 3.11 隔离（framework 专属代码不泄漏）
8. runtime 启动/关闭顺序（resync→start；shutdown→dispose；失败逆序清理）
9. M2 回归（Reminder 禁用时 pipeline 不变）
10. 无 M4+ 实现；privacy（无 QQ 触碰）
