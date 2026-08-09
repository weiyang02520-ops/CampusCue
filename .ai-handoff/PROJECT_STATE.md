# PROJECT_STATE.md

> 人工项目阶段事实源。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0（Architecture / Audit）
- status：**AWAITING_EXTERNAL_REVIEW**（文档已提交，等待外部 ChatGPT 审核）

## completed

- M0 全部文档：docs/v2/00-19 + adr/（ADR-001 ~ ADR-010）
- AstrBot 固定基准 commit `30e20318c` 研究完成（9 条链路，全部 CONFIRMED）
- CampusCue V1 完整审计（25 文件 + 前端 + 测试 + PROGRESS 七轮修复）

## in_progress

- 无（M0 完成，等待审核）

## blocked

- 无

## verified

- AstrBot 基准 commit 锁定（本地 git checkout 验证）
- V1 仓库克隆 + 关键文件读取（main.py / PROGRESS / campuscue/ 模块规模 / 耦合 import 清单）
- 两轮独立代理研究：AstrBot 9 条链路 + V1 25 文件审计，结论均为 CONFIRMED（读码所得）

## unverified / known unknowns

- V1 `extract()` LLM 抽取从未在测试跑过（B13）——V2 必须补
- V1 profile.timezone 字段存在但解析/前端均硬编码 Asia/Shanghai（B12）——V2 必修
- AstrBot 发送管线流式降级、Dashboard 认证细节未深入研究（非 V2 需要，见 03 文档 §9 边界）
- NapCat 真实联调未做（M1 验收阶段做 REAL ENV VERIFIED）

## architecture_decisions

- 见 docs/v2/18_DECISIONS.md（ADR-001 ~ ADR-010），核心 5 条：
  1. OneBot 协议不泄漏进 Domain（converter 边界）
  2. DB = 唯一业务事实源
  3. Realtime（SSE）只是通知传输，不是状态源
  4. 零 AstrBot 依赖（Anti-AstrBot Gate）
  5. TaskService 唯一创建/变更入口

## next_gate

- 外部 ChatGPT 审核 M0 文档（重点：03_ASTRBOT_ARCHITECTURE、05_V2_ARCHITECTURE、17_MILESTONES、18_DECISIONS）
- 审核通过 → 进入 M1（Independent QQ Runtime）

## external_review_focus

- M0 文档是否诚实（有无把 UNKNOWN 写成 CONFIRMED）
- 架构方向是否成立（轻量 EventBus/Router、OneBotAdapter 边界、TaskService 唯一入口）
- M1 最小实现范围是否真的最小
- ADR 是否合理
