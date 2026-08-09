# PROJECT_STATE.md

> 人工项目阶段事实源。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0 = **PASS**（外部审核条件性通过，M0.1 全部 finding 已修复）
- M1 = **READY_NOT_STARTED**（等待外部审核确认后开始）
- status：**M0.1 REVIEW FIX COMPLETE，AWAITING M1 GO**

## completed

- M0 全部文档：docs/v2/00-19 + adr/（ADR-001 ~ ADR-010）
- AstrBot 固定基准 commit `30e20318c` 研究（9 条链路，CONFIRMED）
- CampusCue V1 完整审计
- **M0.1 外部审核修复**（B~N 共 14 项 finding 全部应用）
- **双 Memory 建立**：docs/context/CHATGPT_MEMORY.md + AGENT_MEMORY.md

## in_progress

- 无（M0.1 完成，等待外部审核 M1 GO）

## blocked

- 无（M1 启动依赖外部审核确认）

## verified

- 外部审核 verdict：M0 架构方向 PASS；文档精度 CHANGES_REQUESTED → 已全部修复（见 HANDOFF finding 清单）
- AstrBot 基准 commit 锁定；V1 仓库克隆
- 文档一致性检查（AD 检查项）：见 M0.1 轮验证记录

## unverified / known unknowns

- V1 `extract()` LLM 抽取从未在测试跑过（B13）——M2 修
- V1 profile.timezone 字段存在但解析/前端均硬编码 Asia/Shanghai（B12）——M2 修
- NapCat 真实联调未做（M1 验收 REAL ENV）
- V2 无任何代码，无 REAL ENV 验证

## architecture_decisions

- 见 docs/v2/18_DECISIONS.md + adr/（ADR-001~010）+ M0.1 修正（Reverse WS server 所有权、Provider 前移 M2、有界队列、transport dedup、Outbound 直连等，详见 CHATGPT_MEMORY §9 REJECTED/SUPERSEDED）

## next_gate

- 外部 ChatGPT 读取 GitHub（M0.1 提交）→ 确认 M0 PASS → 发布 M1 prompt

## external_review_focus（M0.1 审核点）

- 14 项 finding 是否全部正确修复
- 双 Memory 是否满足 high-fidelity recovery
- Milestone dependency（Provider 在 M2）是否一致
