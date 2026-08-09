# 11_API_SPEC.md

> CampusCue V2 初版 REST API 契约。M0 只做文档；M5 实现。标注 [DRAFT] 的字段 M5 定稿。
> 依据：V1 API 能力清单（[02_V1_AUDIT](02_V1_AUDIT.md)）+ 产品需求（[01_PRODUCT_VISION](01_PRODUCT_VISION.md)）。

## 通用约定

- Base path：`/api/v1`（M5 定稿是否保留版本段）
- 认证：默认仅监听 `127.0.0.1`；若允许 LAN，必须启用 token/密码认证（M5 定稿，见 [14_SECURITY_PRIVACY](14_SECURITY_PRIVACY.md)）
- 时间：一律 ISO 8601 with timezone（`2026-08-14T23:59:00+08:00`）
- 错误响应：
```json
{ "detail": "human readable message", "code": "TASK_DUPLICATE" }
```
- 分页（列表接口）：`limit`（默认 50，最大 200）+ `offset`，响应含 `total`

## 资源：Tasks

| Method | Path | 说明 | 状态 |
|---|---|---|---|
| GET | `/tasks` | 任务列表；查询参数 `status`、`category`、`course`、`source_id`、`deadline_from`、`deadline_to`、`q`（搜索）、`limit/offset` | M5 |
| POST | `/tasks` | 创建任务；重复（dedup_key 冲突）返回 409 | M5 |
| GET | `/tasks/{id}` | 任务详情（含 extraction 溯源引用） | M5 |
| PATCH | `/tasks/{id}` | 局部更新（title/category/course/deadline/status/priority）；deadline 变化触发 Reminder 重建 | M5 |
| DELETE | `/tasks/{id}` | 删除任务 + 清理提醒 | M5 |
| POST | `/tasks/{id}/complete` | 标记完成（取消提醒） | M5 |
| POST | `/tasks/{id}/dismiss` | 忽略（取消提醒） | M5 |

请求体（Task 草案见 [06_DOMAIN_MODEL](06_DOMAIN_MODEL.md)）：
```json
{
  "title": "第三章作业",
  "category": "homework",
  "course": "高等数学",
  "deadline": "2026-08-14T23:59:00+08:00",
  "priority": "normal",
  "description": null,
  "source_id": null
}
```

## 资源：Sources

| Method | Path | 说明 |
|---|---|---|
| GET | `/sources` | 来源列表（enabled/auto_extract 状态） |
| POST | `/sources` | 添加来源（平台 + conversation_id） |
| PATCH | `/sources/{id}` | 启用/禁用、auto_extract、context_window、privacy_policy |
| DELETE | `/sources/{id}` | 删除来源（不删任务；任务保留 source 快照引用） |
| POST | `/sources/{id}/test` | 自检：是否可向该来源发送（连通性） |

## 资源：Messages（消息页数据）

| Method | Path | 说明 |
|---|---|---|
| GET | `/messages` | 已处理消息列表（分页）；查询参数 `source_id`、`had_task`、`confidence_min` |
| GET | `/messages/{message_id}` | 单条：原消息、识别时间、提取结果、创建的任务、为何未创建（如跳过原因） |

设计：默认只保留"被识别为事务候选"的消息（隐私，见 [14_SECURITY_PRIVACY](14_SECURITY_PRIVACY.md)）。不做完整 QQ 聊天记录。

## 资源：Reminders

| Method | Path | 说明 |
|---|---|---|
| GET | `/reminders` | 提醒列表（fire_at 按用户时区）；查询参数 `status`、`task_id` |
| POST | `/reminders/{id}/cancel` | 取消单条提醒 |

## 资源：Providers

| Method | Path | 说明 |
|---|---|---|
| GET | `/providers` | Provider 列表（**不含** secret 值，只含 secret_reference 名） |
| POST | `/providers` | 添加 ProviderConfig |
| PATCH | `/providers/{id}` | 更新（secret_reference 可换） |
| DELETE | `/providers/{id}` | 删除 |
| POST | `/providers/{id}/test` | 测试连接：发一次最小 chat，返回 latency/ok/error 分类 |

## 资源：Agent

| Method | Path | 说明 |
|---|---|---|
| POST | `/agent/chat` | 发送用户输入 → AgentRuntime → 回复；请求体 `{ "conversation_id": "optional", "message": "..." }` |
| GET | `/agent/threads` | 线程列表（M4 按需） |

## 资源：Settings

| Method | Path | 说明 |
|---|---|---|
| GET | `/settings` | 全局设置（提醒默认偏好、消息保留策略、主题、时区） |
| PATCH | `/settings` | 更新（枚举校验） |

## 资源：System

| Method | Path | 说明 |
|---|---|---|
| GET | `/health` | runtime 状态 / adapter 状态 / DB 可达性 |
| GET | `/system/status` | 诊断：组件状态、最近事件时间戳（供接入页） |
| POST | `/system/backup` | 创建备份（[02_V1_AUDIT](02_V1_AUDIT.md) B：排除 secret/登录态） |
| POST | `/system/restore` | 恢复备份（需 `confirm_replace`，单事务原子替换） |
| GET | `/system/logs` | 诊断日志（分页，脱敏，可选） |

## 资源：Import/Export

| Method | Path | 说明 |
|---|---|---|
| POST | `/system/import` | 导入任务（V1 `示例-导入测试.json` 兼容格式，M5 验证） |
| GET | `/system/export` | 导出任务 |

## Realtime（SSE）

`GET /api/v1/stream`（M5/M6 定稿）——事件类型：

| type | 载荷 | 说明 |
|---|---|---|
| `task.created` / `task.updated` / `task.completed` / `task.dismissed` / `task.deleted` | task 摘要 | 任务变化通知 |
| `reminder.fired` | reminder 摘要 | 提醒触发（UI 可显示 toast） |
| `extraction.updated` | extraction 摘要 | 识别进度（消息页） |
| `connection.updated` | adapter 状态 | 接入页实时状态 |

规则（见 [22 Realtime Source of Truth] 原则，与 [05_V2_ARCHITECTURE](05_V2_ARCHITECTURE.md)）：
- SSE 仅是**变更通知**，前端收到后按需 REST 刷新 canonical state。
- 连接生命周期：cleanup 完整、重连指数退避、日志限频、心跳（如需要）。
- 断线后前端必须 REST 全量 refresh（禁止依赖 SSE 重放作为事实源）。

## 契约与测试

- M5：对上述每个 endpoint 写 contract test（Pydantic 校验 + Service mock）+ integration test（真实 SQLite tmp 库）。
- 409/422/404 等错误路径必须有测试。
