# PROJECT_STATE.md

> 人工项目阶段事实源（canonical，非 append-only）。由工作区 AI 在每个阶段更新；Git 可实时获得的字段（HEAD/visibility）由脚本实时获取，不在此维护。

## project

- 名称：CampusCue V2（课讯）
- 定位：面向大学生的校园事务 AI Agent 平台（校园事务管理 + AI 助手 + QQ 自动信息入口）
- 重新立项原因：V1 跑在 AstrBot Runtime 上（AstrBot fork + CampusCue 业务层），V2 独立自研

## goal

从零重写 CampusCue 为独立平台：不依赖 AstrBot 运行时，保留 V1 已验证的业务行为（三级抽取/去重/提醒/备份），实现 QQ（NapCat/OneBot v11）→ 任务 → 提醒 → WebUI 完整闭环，AI 助手通过 Tool 访问真实数据。

## current_milestone

- M0 = **PASS**；M1 = **PASS**（含 REAL ENV）；M2a = **PASS**；**M2b.1 = PASS（最终）**
- **M2b.2 = REAL_ENV_ACCEPTANCE_COMPLETE — AWAITING_EXTERNAL_M2_FINAL_REVIEW**
- **M2 = AWAITING_EXTERNAL_FINAL_REVIEW；M2 FINAL = NOT PASS（等外部复核）**
- M3+ = NOT_AUTHORIZED
- status：**AWAITING_EXTERNAL_M2_FINAL_REVIEW**

## completed

- M0 / M0.1 / M0.2（PASS）
- M1 / M1.1 / M1.2 / M1.3（PASS）
- M2a / M2a.1 / M2a.2（PASS）
- M2b.1 / M2b.1.1 / M2b.1.2（PASS）
- **M2b.2（REAL ENV ACCEPTANCE COMPLETE）**：真实 QQ 群消息 → NapCat（Framework）→ Reverse WS → AI-first pipeline → DeepSeek → SQLite 全链路；测试 A-E 全 PASS（hello 共存/明确任务 deadline 精确/普通聊天 skipped/语义重复/重启持久化 + 自动重连）

## in_progress

- 无（M2b.2 验收完成，checkpoint 后停止，等待外部 M2 最终复核）

## blocked

- **M3+ 仅阻塞于 M2 外部最终复核**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **316 tests passed**；package isolation PASS（fresh venv `.venv-m2iso` + tzdata）；Anti-AstrBot PASS
- **REAL ENV VERIFIED（M2b.2，2026-08-10）**：真实 QQ 群消息全链路；structured_mode=json_fallback（DeepSeek）；deadline `2026-08-14 15:59 UTC` 精确；duplicate 不创建第二 Task；重启 DB 持久化 + NapCat 自动重连
- 外部审核状态：**awaiting**（M2a/M2b.1 PASS；M2b.2 REAL ENV 待最终复核）

## unverified / known unknowns

- 无阻塞性未知；真实模型 course 提取依赖消息原文是否含课程名（REAL_MODEL_VARIANCE，非 bug）
- 无迁移框架；未来 schema 版本需人工迁移

## architecture_decisions

- ADR-001 ~ ADR-013（docs/v2/adr/，含 ADR-013 AI-First Extraction）

## next_gate

- 外部 ChatGPT M2 最终复核（读取 GitHub HEAD + REAL ENV 证据）→ PASS 则 **M3（Reminder）授权**

## external_review_focus（M2b.2 REAL ENV 复核点）

1. REAL QQ 群消息完整链路（NapCat → WS → pipeline → DeepSeek → SQLite）
2. structured_mode=json_fallback（DeepSeek 不支持 json_schema，回退共享 canonical 语义契约）
3. deadline 精确 `2026-08-14 15:59 UTC`（TimeNormalizer）
4. provider/model provenance（openai_compatible / deepseek-chat）
5. 普通聊天 → skipped 无 Task 无输入泄漏（privacy）
6. 语义重复 → 不创建第二 Task
7. 重启 DB 持久化 + NapCat 自动重连
8. M1 hello 共存
9. 用户大号保护（未触碰；测试用独立小号 bot）
10. 无 CampusCue source changes（纯验收轮）
