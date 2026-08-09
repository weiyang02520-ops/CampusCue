# 00_REFERENCE_BASELINE.md

> M0 研究基准固定记录。本文件由 M0 建立，后续若需变更基准必须先由外部审核确认。

## 时间

- 研究日期：2026-08-09

## AstrBot 参考仓库

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/AstrBotDevs/AstrBot |
| 固定研究 commit | `30e20318cbaaa2e1ba57f3e0eee265d9ee98115c` |
| commit 说明 | `fix: cancel stopped agent runs immediately (#9602)` |
| 本地副本 | `工作区1/github-research/AstrBot`（已 checkout 到该 commit） |

除非外部审核明确要求"重新研究 AstrBot 最新 HEAD"，否则 AstrBot 上游更新不影响本项目的参考基线。

## CampusCue V1 仓库

| 项 | 值 |
|---|---|
| 仓库 | https://github.com/weiyang02520-ops/CampusCue |
| 当前 HEAD | `db35d77` `feat: publish CampusCue source` |
| 可见性 | public（2026-08-09 创建） |
| 本地审计副本 | `工作区1/campuscue-v1-audit`（只读克隆） |

注意：V1 仓库为单 commit 快照发布（git 历史仅 1 条），因此 V1 的历史 Bug 证据主要来自：
- PROGRESS.md（详细记录了七轮修复）
- campuscue/ 源码注释
- tests/ 中的回归测试

## 研究边界

M0 允许阅读：

- AstrBot（固定 commit）：启动 / 事件 / 平台 / OneBot / Pipeline / Provider / Agent / Cron / Dashboard 后端，见 `19_REFERENCE_INDEX.md` 中的文件清单
- CampusCue V1：README / PROGRESS / main.py / campuscue/ / tests/ / campuscue/web/

M0 禁止：

- 创建 V2 Runtime 正式代码
- 创建 OneBotAdapter / EventBus / Agent / Provider / Tool 正式实现
- 创建 V2 WebUI
- 大规模修改 V1 或删除 V1

M0 只产出：研究、审计、设计文档（docs/v2/）与交接文档（.ai-handoff/）。

## 版本事实

- CampusCue V1 声明基于 AstrBot `v4.26.7`（README）
- 实际 fork 结构：`main.py` 使用 AstrBot `InitialLoader` 启动整个 AstrBot core，CampusCue 业务层挂在上面（[CONFIRMED] `main.py:44-47`、`campuscue/__init__.py`）
