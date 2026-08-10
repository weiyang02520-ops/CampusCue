# 06_DOMAIN_MODEL.md

> CampusCue V2 领域模型定义。M0 为草案；M2-M4 实现时可微调，但字段语义变更须记 ADR。

## CampusEvent（跨边界统一事件）

| 字段 | 类型 | 说明 |
|---|---|---|
| event_id | str | 事件唯一 ID（UUID） |
| trace_id | str | 追踪链 ID（同一条消息的整条处理链共享） |
| platform | str | `onebot`（第一版唯一） |
| adapter_id | str | Adapter 实例 ID |
| event_type | str | `group_message` / `private_message` / `system`（第一版） |
| self_id | str | 机器人自身 ID |
| message_id | str | 平台消息 ID |
| conversation_id | str | 会话 ID（群号 / QQ 号） |
| conversation_type | str | `group` / `private` |
| group_id | str \| None | 群消息时必填 |
| sender_id | str | 发送者 ID |
| sender_name | str | 发送者昵称（可为空） |
| timestamp | datetime | 事件时间（timezone-aware） |
| text | str | 纯文本（已拼合） |
| segments | list[MessageSegment] | 原始消息段（第一版含 text/at/reply/image 解析） |
| reply_to_message_id | str \| None | 引用回复目标 |
| metadata | dict | 扩展元数据（不承载业务状态） |
| raw_ref | dict \| None | 受限原始载荷引用（M1 允许调试用，不进业务） |

原则：Adapter 边界内完成 OneBot JSON → CampusEvent；业务层只见 CampusEvent。

## MessageSegment（第一版）

| type | 说明 |
|---|---|
| text | 纯文本 |
| at | @成员 |
| reply | 引用回复（保留 message_id + 摘要） |
| image | 图片（保留 URL/file_id，M1 不下载） |

## Source（消息来源）

| 字段 | 说明 |
|---|---|
| id | UUID |
| platform | onebot |
| conversation_id | 群号 / QQ 号（canonical identity = (platform, conversation_id) + DB 唯一约束，ADR-012-C） |
| name | 显示名 |
| enabled | 是否允许自动处理 |
| auto_extract | 是否自动抽取（默认 true） |
| context_window | 上下文窗口（条数，默认小） |
| privacy_policy | 隐私策略（retention 等级） |
| created_at / updated_at | 时间戳 |

## Task

| 字段 | 说明 |
|---|---|
| id | UUID |
| title | 标题 |
| description | 描述（可空） |
| category | `homework` / `exam` / `competition` / `activity` / `notice` / `other` |
| course | 课程 / 归属（可空） |
| deadline | 截止时间（timezone-aware，可空） |
| status | `pending_confirm` / `pending` / `done` / `dismissed`（ADR-012-A 唯一枚举；pending_confirm=低置信度待确认，dismissed 仍参与 dedup 历史） |
| priority | `high` / `normal` / `low`（默认 normal） |
| source_id | 来源（Source.id） |
| source_message_id | 平台消息 ID |
| source_text_reference | 原始消息引用（保留可核对） |
| confidence | 抽取置信度（0-1） |
| dedup_key | 去重指纹（组合指纹） |
| created_at / updated_at | 时间戳 |

## Extraction（抽取记录）

| 字段 | 说明 |
|---|---|
| id | UUID |
| source_message_id | 关联消息 |
| raw_result | LLM 原始结构化输出（JSON） |
| normalized_result | 规范化后结果（JSON） |
| confidence | 置信度 |
| provider / model | 使用的 Provider 与模型 |
| status | `success` / `skipped` / `error` / `duplicate`（闭集枚举） |
| audit | 结构化 JSON：{"l1":{},"l3":{},"l4":{},"l5":{},"outcome":{}}（ADR-012-B） |
| error | 错误信息（脱敏） |
| created_at | 时间戳 |

## Reminder

| 字段 | 说明 |
|---|---|
| id | UUID |
| task_id | 关联任务 |
| trigger_at | 触发时间 |
| type | `deadline` / `day_before` / `hours_before` 等 |
| status | `scheduled` / `fired` / `cancelled` |
| last_run / error | 运行状态 |
| job_id | APScheduler job id（运行时派生，可重建） |

## ProviderConfig

| 字段 | 说明 |
|---|---|
| id / name | 标识 |
| provider_type | `openai_compatible`（第一版） |
| base_url / model | 端点与模型 |
| temperature / max_tokens / max_context_tokens / timeout | 参数 |
| secret_reference | 密钥引用（env 变量名），**绝不存真实 key** |
| enabled | 是否启用 |

## Tool / ToolResult

```python
class ToolDefinition:
    name: str
    description: str
    input_schema: dict  # JSON Schema
    permission: str     # 第一版统一 "task" 域
    async def execute(**kwargs) -> ToolResult

class ToolResult:
    ok: bool
    content: str   # 给 LLM 看的文本
    data: dict | None
    error: str | None
```

## AgentThread（M4 按需）

第一版不需要 30 字段。需要时再定义（conversation_id、messages 摘要、budget 状态）。

## 存储映射（草案，M2 定稿）

tables: `sources`, `tasks`, `extractions`, `reminders`, `provider_configs`, `settings`。
`messages` 表视隐私策略决定（默认不存全文，只存被识别任务的来源消息）。
**J 修正：`sources` 与 `extractions` 表及对应 Repository（SourceRepository/ExtractionRepository）在 M2 即实现**（Task Pipeline 的 SourcePolicy 与 extraction audit 依赖它们），不等 M5。`reminders`/`provider_configs` 表随 M3/M2a 建。
