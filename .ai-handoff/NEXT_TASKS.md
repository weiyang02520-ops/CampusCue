# NEXT_TASKS.md

> 未来任务清单（YAGNI 存放处 + 各 Milestone 预备）。**不要提前实现**，除非对应 Milestone 开始。

## M1 状态（2026-08-09）

- [x] V2 独立 implementation root（v2/，ADR-011）+ pyproject + Anti-AstrBot Gate
- [x] CampusRuntime / CampusEvent / 有界 EventBus / Router / EchoHandler
- [x] OneBotAdapter（Reverse WS SERVER + token + 帧分类 + echo correlation + generation + dedup）
- [x] unit 49 + integration 16 全绿；package isolation PASS
- [ ] **REAL ENV**：真实 NapCat 联调（阻塞：本机无 NapCat）——需用户提供环境：
  1. 安装/启动 NapCat（QQ 登录）
  2. 配置反向 WS 客户端指向 `ws://127.0.0.1:6199/ws`（可设 token）
  3. `CAMPUSCUE_ONEBOT_TOKEN=...`（如配置了）`CAMPUSCUE_DIAGNOSTIC=1 python -m campuscue` 启动
  4. 真实 QQ 群发送 `hello` → 验证收到 `received: hello`
  5. 关闭 diagnostic；HANDOFF 只记脱敏 ID；更新状态 M1 PASS

## M2 预备（M1 PASS + 外部审核后启动）

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
