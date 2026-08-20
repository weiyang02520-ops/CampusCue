# 11_API_SPEC.md — M5 Implemented Contract

> CampusCue V2 REST + Realtime API。M5 已实现；本文档描述实际代码契约。
> Base path：`/api/v1`

## 通用约定

- 所有业务 API 位于 `/api/v1`。
- 健康检查 canonical：`GET /api/v1/health`。
- 认证：默认 loopback 无认证；`CAMPUSCUE_REQUIRE_AUTH=1` 或非 loopback host 时要求 `Authorization: Bearer <token>`。
- 时间：所有输入/输出 datetime 均为 ISO 8601 且带 timezone；存储 canonical 为 UTC。
- 分页：`limit` 默认 50，最大 200，`offset >= 0`。列表响应：`{items,total,limit,offset}`。
- 错误响应：`{"detail": "...", "code": "..."}`；常见 code：`NOT_FOUND`、`CONFLICT`、`VALIDATION_ERROR`、`UNAUTHORIZED`、`SERVICE_UNAVAILABLE`。

## Tasks

| Method | Path | 说明 |
|---|---|---|
| GET | `/tasks` | filters: status/category/course/source_id/deadline_from/deadline_to/q/limit/offset |
| POST | `/tasks` | 人工创建任务，经 TaskService；可指定 source_id（必须存在） |
| GET | `/tasks/{id}` | 任务详情 |
| PATCH | `/tasks/{id}` | 局部更新；deadline 省略=不变、null=清除、datetime=替换 |
| DELETE | `/tasks/{id}` | 删除任务 + 清理提醒 |
| POST | `/tasks/{id}/complete` | 完成（取消提醒） |
| POST | `/tasks/{id}/dismiss` | 忽略（取消提醒） |

## Sources

| Method | Path | 说明 |
|---|---|---|
| GET | `/sources` | 未删除来源列表 |
| POST | `/sources` | 创建来源；重复 platform+conversation → 409 |
| PATCH | `/sources/{id}` | 更新 name/enabled/auto_extract/context_window/privacy_policy |
| DELETE | `/sources/{id}` | 软删除（保留 Task/Extraction provenance FK） |
| POST | `/sources/{id}/test` | 当前为 Adapter 连通性检查，不发送垃圾消息 |

## Messages

- 数据来源为 `extractions` 投影，不保存完整 QQ 历史。
- `GET /messages` filters: source_id/had_task/confidence_min/limit/offset。
- `GET /messages/{id}` 中 id 是 extraction row id。
- 未保留原文时返回 `text_retained=false, retained_text=null`。

## Reminders

- `GET /reminders` filters: status/task_id/limit/offset。
- `POST /reminders/{id}/cancel` 走 ReminderService。

## Providers

- `GET/POST/PATCH/DELETE /providers` + `POST /providers/{id}/test`。
- 永远不返回 secret value；只返回 `secret_reference`。
- 复用 Provider Foundation 与 canonical validation。

## Agent

- `POST /agent/chat` 请求：`{source_id, conversation_id?, message}`。source_id 必填；Runtime 构造 trusted context，不信任 HTTP 注入的 provenance。
- `GET /agent/threads` 返回当前 in-memory threads 摘要；重启丢失是 M4 first-version 设计允许。

## Settings

- `GET /settings` / `PATCH /settings`。
- 持久化在 schema v3 `settings` 表。
- 字段：`timezone`、`theme`、`message_retention_days`、`reminder_default_enabled`、`reminder_min_lead_seconds`、`reminder_quiet_start_hour`、`reminder_quiet_end_hour`。
- `timezone` 修改返回 `restart_required`。

## System

- `GET /api/v1/health`：runtime/database/adapter/reminders/agent/api。
- `GET /system/status`：组件/feature flags/provider/adapter/uptime。
- `GET /system/logs`：bounded in-memory redacted diagnostic ring buffer。
- `POST /system/backup`：逻辑 JSON 备份（含业务表，不含 secret/登录态）。
- `POST /system/restore`：需 `confirm_replace=true`，单事务替换，成功后 resync reminders。
- `POST /system/import`：兼容 `campuscue.tasks` V1 格式，per-item 结果。
- `GET /system/export`：导出任务。

## Realtime (SSE)

- `GET /api/v1/stream`：SSE notification only，无 replay。
- 事件：`task.created/updated/completed/dismissed/deleted`、`reminder.fired/cancelled`、`extraction.updated`、`connection.updated`。
- 每个 subscriber 独立 bounded queue；慢 subscriber 标记 closed、从 active registry 移除，并唤醒正在运行的 stream generator 使 SSE 连接真正结束。
- 心跳：`: ping`（由 `ApiConfig.sse_heartbeat_interval` / `CAMPUSCUE_API_SSE_HEARTBEAT` 控制，默认 15s）。
- 断线后客户端必须 REST refresh canonical state。

### Realtime event producer matrix

| Event | Producer | Commit point | Payload | Evidence |
|---|---|---|---|---|
| `task.created` / `task.updated` / `task.completed` / `task.dismissed` / `task.deleted` | `TaskService` | task mutation repository commit | task id/status/deadline/updated time | TaskService/API tests |
| `reminder.fired` / `reminder.cancelled` | `ReminderService` | reminder mutation commit | reminder id/task id/status/time | Reminder tests |
| `extraction.updated` | `TaskPipeline` | extraction row commit | extraction/source/message/status/confidence | Pipeline tests |
| `connection.updated` | `OneBotAdapter` optional neutral connection callback | active connection set/cleared | adapter id + connected flag | real `_handle_connection` lifecycle test |

Realtime publication is derived notification only. Publisher failures are
isolated after the business mutation and do not change a successful API result.
