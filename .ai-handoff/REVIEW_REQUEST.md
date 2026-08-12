# REVIEW_REQUEST.md

> M2 FINAL Continuity 复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M2 Final Continuity Cleanup）复核本轮纯文档修复。

## 背景

外部 ChatGPT 已对 M2b.2 技术审核 = PASS（真实链路接受）。M2 FINAL 暂为 CHANGES_REQUESTED——仅因连续性/文档含 stale pre-M2b.2 状态。本轮为**纯文档/连续性修复，零生产源码修改**。

## 请求审核内容（8 项复核点）

1. **AGENT_MEMORY 全文件语义一致**：无 stale 活动状态——统一为 M0/M1/M2a/M2b.1/M2b.2 = PASS，M2 = TECHNICALLY_COMPLETE AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW，M3 = NOT_AUTHORIZED
2. **README 能力现状**：Implemented（M1 QQ runtime + M2 AI-first task extraction）/ Not yet implemented（M3 Reminder / M4 Agent / M5 API / M6 WebUI）明确区分，无"当前仅 M1"残留
3. **README 架构双路径**：EchoHandler（M1）+ TaskPipeline → Provider → TimeNormalizer → TaskService → SQLite（M2）
4. **README 依赖准确**：以 pyproject.toml 为 canonical source，不手动断言
5. **pyproject description**：milestone-neutral（`independent campus affairs AI agent platform`）；version/deps/packages/build 未动
6. **NapCat EPIPE 措辞**：2026-08-10 本机观察（前台 EPIPE / 重定向成功），非普适规则
7. **用户大号保护事实保留**：PROTECTED、独立 bot 账号、禁止批量 kill、账号角色需证明——无真实 ID
8. **生产源码零修改**（v2/src/、tests/ 未动）

## 风险与未验证项（诚实声明）

- 本轮**未重跑测试**（零生产源码修改）；316 passed 为 M2b.2 历史 Workspace Agent 证据
- REAL ENV 无新操作（M2b.2 验收保留）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
