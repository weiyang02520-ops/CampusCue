# REVIEW_REQUEST.md

> M0 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 直接审核。

## 请求审核内容

**重点文档（按优先级）**：

1. `docs/v2/03_ASTRBOT_ARCHITECTURE.md` —— AstrBot 研究结论（是否与源码一致，有无推断冒充确认）
2. `docs/v2/05_V2_ARCHITECTURE.md` —— V2 目标架构（模块拓扑 / 依赖方向 / 红线）
3. `docs/v2/17_MILESTONES.md` —— M1-M7 范围与 PASS 标准（M1 是否真的最小）
4. `docs/v2/18_DECISIONS.md` —— ADR-001~010（决策是否合理）
5. `docs/v2/02_V1_AUDIT.md` + `19_REFERENCE_INDEX.md` —— V1 审计结论（耦合评级 / REUSE vs REWRITE 判断）
6. `docs/v2/10_TASK_PIPELINE.md` / `10_REMINDER.md` / `08_PROVIDER_AND_AGENT.md` / `11_API_SPEC.md` —— 各子系统设计

## 需要确认的结论（关键判断）

1. V1 = AstrBot Runtime + CampusCue 业务层（证据：main.py:44-47、campuscue/__init__.py、astrbot/ 完整目录、底座 4 处侵入）——结论是否成立
2. V1 业务核心（L1/L3/dedup/backup/transfer/web 纯函数）与 AstrBot 零耦合可带走——是否同意
3. V1 高耦合点清单（store/tools/reminders/setup）→ REWRITE——是否同意
4. AstrBot 值得学的 10 条 / 不该照搬的 10 条（03 文档 §10-11）——有无遗漏或误判
5. V2 轻量架构（EventBus=asyncio.Queue、Router 直线流程、无 Plugin System、TaskService 唯一入口）——是否成立
6. M1 最小范围（Runtime/Event/CampusEvent/Bus/Router/OneBotAdapter/Echo）——是否真最小，有无遗漏关键件
7. ADR-001~010 有无错误或缺失

## 风险与未验证项（诚实声明）

- M0 零代码、零测试运行、零真实环境验证
- B12（V1 时区硬编码）、B13（V1 LLM 测试缺口）为审计新发现，未在 V1 修复
- AstrBot 发送管线流式细节、Dashboard 认证细节未深研（非 V2 需要）
- NapCat 真实联调未做（M1 验收）

## Real Verified vs Not

- **CONFIRMED**（读码/运行验证）：AstrBot 9 条链路调用链与行号、V1 模块结构/耦合清单、Git 状态
- **NOT VERIFIED**：V1 extract() 真实 LLM 路径（从未被测试）、NapCat 真实联调、V2 任何设计（均为文档）

## 无视觉审核需求

本轮无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
