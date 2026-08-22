# 课讯 CampusCue

**校园通知，自动变成待办。**

课讯 CampusCue 是面向校园群聊的本地优先事务抽取工具。它静默读取群消息，通过规则预筛、大模型结构化抽取和本地去重，把作业、考试、比赛、活动与通知转换为带截止时间的任务，并在识别后主动推送。

本项目是 2026 年湖北省首届“火山杯”AI 创客大赛青年 AI 创新赛道参赛项目。

## 当前状态

- QQ 群接入：NapCat / OneBot v11
- 三级抽取：规则预筛、LLM 结构化提取、时间落地与去重
- Vue 3 任务看板：筛选、编辑、追踪、导入导出与提醒管理
- 本地 SQLite 存储，WebUI 默认仅监听 `127.0.0.1:6185`
- CampusCue 自动化测试 399 项（含 18 项 AstrBot 入口测试）
- 前端状态与网络测试 9 项
- Windows 安装、升级、卸载和数据保留流程已验证

详细进展、验收结果和已知风险见 [PROGRESS.md](PROGRESS.md)。产品背景与技术取舍见 [项目简介.md](项目简介.md)。安装和使用方法见 [使用文档.md](使用文档.md)。

> CampusCue V2 的 M7 Final 已通过 External Review：bounded Agent confirmation、source-bound thread isolation、真实高层 tool activity 和可复现的本地演示闭环均已完成。Real QQ M7 E2E 为 NOT_RUN（accepted limitation）。详见 [V2 Quick Start](docs/demo/QUICKSTART.md)。

## 架构

消息进入旁路处理管道后，依次经过：

1. 本地规则预筛，过滤绝大多数闲聊，不消耗模型 token。
2. 候选消息发送到已配置的大模型，强制输出结构化任务 JSON。
3. 本地完成相对时间解析、相似任务去重和置信度分级。
4. 任务写入本地数据库，并按配置推送和安排截止提醒。

每条任务保留原始消息与模型判断理由，方便用户核对和修正。

## 技术栈

- Python 3.12、FastAPI、SQLModel、SQLite、APScheduler
- Vue 3、Vite
- NapCat / OneBot v11
- AstrBot v4.26.7 底座

自研功能集中在 `campuscue/`，包括抽取管道、领域模型、API、提醒、推送、备份恢复和任务看板。项目基于 AstrBot 二次开发，保留其原始版权和许可证信息。

## 快速开始

Windows 用户可双击：

```text
安装课讯.bat
启动课讯.bat
```

开发方式：

```powershell
uv sync
uv run main.py
```

WebUI 默认地址：`http://127.0.0.1:6185`。

运行前需要自行配置 QQ 接入和模型服务凭据。凭据通过本地 `.env` 或环境变量提供，不应提交到仓库。

## 隐私边界

完整群聊、任务数据库和历史记录保存在本机。规则预筛在本地执行；只有通过预筛、需要模型判断的候选消息及必要上下文会发送给用户配置的模型服务。仓库不包含任何实际 API Key、QQ 登录态、运行数据库或私人消息。

## 上游与许可证

CampusCue fork 自 [AstrBot](https://github.com/AstrBotDevs/AstrBot) v4.26.7。仓库按 [AGPL-3.0](LICENSE) 发布。AstrBot 的原始多语言说明仍保留在 `README_zh.md`、`README_ja.md` 等文件中。

