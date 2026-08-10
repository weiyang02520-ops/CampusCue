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
- M2 = **IN_PROGRESS**：M2a + M2a.1 + M2a.2（Data + Provider Foundation 全部完成）— **AWAITING_EXTERNAL_FINAL_REVIEW**
- **M2b = NOT_STARTED / NOT_AUTHORIZED**（等 M2a 外部最终确认）
- M2 最终 = NOT PASS（等 M2b）
- status：**AWAITING_EXTERNAL_M2A_FINAL_REVIEW**

## completed（M2a 系列全部）

- M2a：ADR-012 契约锁定 + storage（SQLAlchemy/aiosqlite/schema 版本）+ Repository×4 + SourceService + providers 包 + bootstrap 脚本
- M2a.1：provider.test 真实路径、timeout 契约、枚举 repository+CHECK 双层、schema 零变更拒绝、Clock 注入、secret_reference 早校验、get_by_id、严格解析、状态先分类
- M2a.2：secret/numeric/request-override 共享校验、ORM 去墙钟默认、HANDOFF/PROJECT_STATE canonical 修复

## in_progress

- 无（M2a.2 完成，checkpoint 后停止）

## blocked

- **M2b 仅阻塞于 M2a 外部最终确认**（无其他阻塞）

## verified（Workspace Agent 报告；外部审核待复核）

- **203 tests passed**（M1 87 旧全绿 + M2a 系列 116 新增）；package isolation PASS（fresh venv）；Anti-AstrBot PASS
- REAL ENV VERIFIED（M1.2，2026-08-10，NapCat v4.18.18 + 真实 QQ）——**保留自 M1.2，非本轮新验证**
- 外部审核状态：**awaiting**（M2a.1 已 PASS；M2a.2 待复核）

## unverified / known unknowns

- 真实 Provider（如 Ark）json_schema 支持度与 timeout 语义（M2b 真实验收）
- 无迁移框架；未来 schema 版本需人工迁移

## architecture_decisions

- ADR-001~012（docs/v2/18_DECISIONS.md + adr/）

## next_gate

- 外部 ChatGPT M2a 最终复核 → PASS 则 **M2b 授权**（Task Extraction Pipeline + 真实 Provider + 真实 QQ 验收）

## external_review_focus（M2a.2 复核点）

1. secret_reference 单一规则（无重复 regex）
2. 配置数值持久化前拒绝（NaN/Inf/bool 测试 + 未持久化证明）
3. request override 校验先于传输（无 HTTP 调用测试）
4. ORM 无墙钟默认（models 源码断言 + required 时间戳）
5. HANDOFF/PROJECT_STATE canonical（无 append 残留/无 stale 字段）
