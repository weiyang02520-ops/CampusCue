# 18_DECISIONS.md

> 架构决策索引。每份 ADR 为独立文件：`adr/ADR-001.md` ~ `adr/ADR-010.md`。
> 格式：Title / Status / Date / Context / Decision / Alternatives / Reason / Consequences。

| ADR | 决策 | Status | 一句话理由 |
|---|---|---|---|
| [ADR-001](adr/ADR-001.md) | OneBot 协议不泄漏进 Domain | Accepted | converter 边界收敛平台差异，纯函数可测 |
| [ADR-002](adr/ADR-002.md) | Database 是唯一业务事实源 | Accepted | 重启/备份/多端一致性只依赖 DB |
| [ADR-003](adr/ADR-003.md) | Realtime 传输不是状态源 | Accepted | 断线可重放、可补拉，SSE 只做通知 |
| [ADR-004](adr/ADR-004.md) | 无 AstrBot Runtime 依赖 | Accepted | V2 立项根本原因；Anti-AstrBot Gate 扫描 |
| [ADR-005](adr/ADR-005.md) | 第一版无 Plugin System | Accepted | YAGNI，Handler + ToolRegistry 够用 |
| [ADR-006](adr/ADR-006.md) | TaskService 唯一创建/变更入口 | Accepted | 去重与提醒联动只维护一处（V1 B03 教训） |
| [ADR-007](adr/ADR-007.md) | Reminder 调度可完全由 DB 重建 | Accepted | DB 推导调度表永远一致，重启天然正确 |
| [ADR-008](adr/ADR-008.md) | Provider 请求实体承载工具链路 | Accepted | Provider 不感知 agent 循环，可单独测试/替换 |
| [ADR-009](adr/ADR-009.md) | 本地优先，LAN 需重新设计安全模型 | Accepted | 默认 loopback，YAGNI |
| [ADR-010](adr/ADR-010.md) | 时区显式注入，前端不硬编码偏移 | Accepted | V1 B12 教训：可测试性 + 多时区正确 |
