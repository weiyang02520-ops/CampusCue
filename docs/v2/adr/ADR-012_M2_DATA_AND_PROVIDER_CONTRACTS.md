# ADR-012：M2 Data & Provider Contracts

- **Status**：Accepted（M2a）
- **Date**：2026-08-10
- **Context**：M2 实现前，跨文档存在 7 项未解决的不一致（TaskStatus 冲突、Extraction 审计不足、Source 身份、L2 上下文、Provider 默认、secret、UTC 存储）。M2a 必须锁定契约后再实现。
- **Decision**：

| # | 设计锁定 | 决定 |
|---|---|---|
| A | TaskStatus | 唯一枚举：`pending_confirm`（低置信度待确认）/ `pending` / `done` / `dismissed`（参与 dedup 历史）。解决 06（pending/done/dismissed）与 10（pending_confirm）矛盾。全业务用单一枚举，不散字符串 |
| B | Extraction audit | `audit` 结构化 JSON（`{"l1":{}, "l3":{}, "l4":{}, "l5":{}, "outcome":{}}`）；raw_result 可含私密内容，只落本机 DB，永不进日志 |
| C | Source 身份 | canonical identity = `(platform, conversation_id)` + DB 唯一约束（未来平台可能复用数字 ID） |
| D | L2 上下文 | M2 无 messages 表；上下文 = 有界内存 ring buffer（message_id/timestamp/text 最小字段），重启即失；DB 仍是唯一事实源 |
| E | Provider 默认 | 0 enabled → NoProviderConfiguredError；1 enabled → get_default；>1 enabled → AmbiguousDefaultProviderError。不静默选第一行 |
| F | Provider secret | 只存 `secret_reference`（环境变量名）；运行时 `os.environ[name]` 解析；secret 值永不进 DB/Git/日志/Memory/异常消息；null 允许（无鉴权端点）；env 变量名保守校验（正则） |
| G | UTC 存储 | 所有跨存储边界的 datetime 必须 timezone-aware；写 UTC、读回 aware UTC；naive datetime 在领域边界拒绝 |

- **Alternatives**：A. 允许 pending_confirm 用布尔标志（拒绝：状态散乱）；C. conversation_id 全局唯一（拒绝：跨平台碰撞）；E. 静默取第一行（拒绝：隐式行为不可调试）；F. 存明文 key（拒绝：违反 ADR-009 与 14_SECURITY_PRIVACY）。
- **Reason**：M2 是数据/Provider 基础层，契约错误会传导到 M2b/M3+；显式锁定让 M2b 只管业务管道。
- **Consequences**：M2a 按本 ADR 实现 schema/repository/provider；M2b 的 L2 用内存 ring buffer；M5 的 API 使用同一契约。
