# NEXT_TASKS.md

> 未来任务清单（YAGNI 存放处 + 各 Milestone 预备）。**不要提前实现**，除非对应 Milestone 开始。

## M1 状态（2026-08-09）

- [x] V2 独立 implementation root（v2/，ADR-011）+ pyproject + Anti-AstrBot Gate
- [x] CampusRuntime / CampusEvent / 有界 EventBus / Router / EchoHandler
- [x] OneBotAdapter（Reverse WS SERVER + token + 帧分类 + echo correlation + generation + dedup）
- [x] unit 49 + integration 16 全绿；package isolation PASS
- [x] **M1.1** 外部源码审核 8 项修复（stale finally/semaphore backpressure/config fail-fast/path 校验/严格响应/诊断模式/raw_message）+ 87 tests 全绿
- [x] **REAL ENV**（2026-08-10）：NapCat v4.18.18 + 真实 QQ 验证完成（私聊/群聊 hello→received:hello、非 hello 无回复、重启自动重连、token 握手）→ **M1 = PASS**

## M2 预备（M1.3 外部确认后启动；当前 NOT_AUTHORIZED）

- [ ] Provider Foundation（BaseProvider / LLMRequest 最小集 / LLMResponse / ProviderError taxonomy / OpenAICompatibleProvider / 最小 ProviderManager / structured output / secret_reference；**独立于 Tool System**）
- [ ] SQLite（sources/tasks/extractions 表）+ SourceRepository / ExtractionRepository / TaskRepository / SourceService / TaskService
- [ ] Task Pipeline（L0-L7；L8 自 M3 接入 TaskService；L9 自 M5 接入）
- [ ] 修 V1 遗留：B12 时区显式注入（TimeNormalizer）、B13 LLM 测试缺口（Provider transport mock）

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
- [ ] M1 未决：NapCat `post-format` 是否默认 array（converter 已拒绝 string 格式；真实环境确认）
