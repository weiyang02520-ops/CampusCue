# DECISIONS.md

> 决策速查（完整 ADR 见 docs/v2/18_DECISIONS.md）。

| ADR | 决策 | 一句话理由 |
|---|---|---|
| 001 | OneBot 协议不泄漏进 Domain | converter 边界收敛平台差异，纯函数可测 |
| 002 | DB 是唯一业务事实源 | 重启/备份/多端一致性只依赖 DB |
| 003 | Realtime 不是状态源 | 断线可重放、可补拉，SSE 只做通知 |
| 004 | 零 AstrBot 依赖 | V2 立项根本原因；Anti-AstrBot Gate 扫描 |
| 005 | 第一版无 Plugin System | YAGNI，Handler + ToolRegistry 够用 |
| 006 | TaskService 唯一创建/变更入口 | 去重与提醒联动只维护一处（V1 B03 教训） |
| 007 | Reminder 调度可完全由 DB 重建 | DB 推导调度表永远一致，重启天然正确 |
| 008 | Provider 请求实体承载工具链路 | Provider 不感知 agent 循环，可单独测试/替换 |
| 009 | 本地优先，LAN 需重新设计安全模型 | 默认 loopback，YAGNI |
| 010 | 时区显式注入，前端不硬编码偏移 | V1 B12 教训：可测试性 + 多时区正确 |
| 011 | V2 代码与 Legacy 物理隔离（v2/ root） | Legacy 冻结为 reference；import 不遮蔽 |
| 012 | M2 数据/Provider 契约锁定 | TaskStatus 单一枚举/Secret 引用/UTC/L2 上下文/恰好一 Provider |
| 013 | AI-First Task Extraction | 正常消息都交 LLM；本地规则只做 hygiene/hints/确定性兜底 |
