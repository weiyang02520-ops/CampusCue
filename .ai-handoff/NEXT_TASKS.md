# NEXT_TASKS.md

> 未来任务清单（YAGNI 存放处 + 各 Milestone 预备）。**不要提前实现**，除非对应 Milestone 开始。
> M0.1 已更新：M1 预备按 Reverse WS server 模型；Provider 前移至 M2。

## M1 预备（外部审核 M0 PASS 后启动）

- [ ] 建立 V2 项目骨架（pyproject/结构），Anti-AstrBot Gate 扫描脚本
- [ ] CampusRuntime 生命周期（07，M1 只激活 Config/EventBus/Router/OneBotAdapter/Echo）
- [ ] CampusEvent / EventBus（有界队列 + 背压）/ Router（06/05）
- [ ] OneBotAdapter：**Reverse WebSocket SERVER**（NapCat 为 client 拨入；host/port/path 可配、token 校验、单 active connection + stale replacement、disconnect cleanup）（04）
  - converter 纯函数优先（Event Frame vs Action Response Frame 分类）
  - sender：text + **echo correlation**（unique echo → pending Future → 匹配回帧；timeout/pending cleanup/断连 fail-all）
  - transport-level dedup（self_id, message_id；bounded + TTL + testable clock）
- [ ] Echo Handler 验收（真实 QQ 收发 hello）

## M2 预备（M1 PASS 后启动）

- [ ] Provider Foundation（BaseProvider / LLMRequest / LLMResponse / ProviderError taxonomy / OpenAICompatibleProvider / 最小 ProviderManager / structured output / secret_reference）
- [ ] SQLite（sources/tasks/extractions 表）+ SourceRepository / ExtractionRepository / TaskRepository / SourceService / TaskService
- [ ] Task Pipeline（L0-L7；L8 自 M3 接入 TaskService；L9 自 M5 接入）

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
