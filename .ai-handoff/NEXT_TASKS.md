# NEXT_TASKS.md

> 未来任务清单（YAGNI 存放处 + M1 预备）。**不要提前实现**，除非对应 Milestone 开始。

## M1 预备（外部审核通过后启动）

- [ ] 建立 V2 项目骨架（pyproject/结构），Anti-AstrBot Gate 扫描脚本
- [ ] CampusRuntime 生命周期（07）
- [ ] CampusEvent / EventBus / Router（06/05）
- [ ] OneBotAdapter（converter 纯函数优先 + WS server + text send）（04）
- [ ] Echo Handler 验收（真实 QQ 收发 hello）

## FUTURE（不做，等真实需求）

- [ ] NapCat 一键安装向导（V1 napcat.py 能力，M7 后评估）
- [ ] 插件系统 / Extension API（ADR-005）
- [ ] 知识库 / RAG / Embedding / Rerank
- [ ] 多平台适配（Telegram/Discord…）
- [ ] SubAgent / Handoff / MCP / Skills / Computer Use
- [ ] 流式对话（M6 后按需）
- [ ] STT / TTS / 图片生成
- [ ] 复杂 RBAC / 微服务 / 分布式任务队列
- [ ] replay 演示回放（V1 replay.py）
- [ ] 消息全文存储 + 检索（当前只存被识别任务来源消息）

## 设计遗留问题（M2-M6 定稿）

- [ ] `messages` 表是否存在（M5 消息页需求定稿时决定）
- [ ] API 认证模型（M5：默认 loopback / LAN 安全模型）
- [ ] Design Tokens 具体值（M6 配合外部视觉审核）
- [ ] import/export 与 V1 示例文件兼容性验证（M5）
