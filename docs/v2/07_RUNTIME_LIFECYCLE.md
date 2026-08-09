# 07_RUNTIME_LIFECYCLE.md

> CampusRuntime 生命周期设计。参考 AstrBot core_lifecycle 的 component wiring 思想，但实现是轻量自研（M1）。

## 状态机

```
CREATED → STARTING → RUNNING → STOPPING → STOPPED
                ↘ FAILED
```

- `FAILED`：startup 任一步骤抛出未恢复错误 → 记录根因 → 清理已启动组件 → 退出码非 0。
- 状态由 `runtime.status` 暴露（health API）。

## 启动顺序

```
1. Config           （加载配置，校验 CAMPUSCUE_ENV）
2. Secrets          （解析 secret_reference → env）
3. DB               （SQLite 连接、migrations、busy_timeout）
4. Repositories     （Task/Source/Extraction/Reminder/ProviderConfig/Setting）
5. Services         （TaskService / ReminderService / NotificationService）
6. EventBus         （async queue + dispatch tasks）
7. Adapter          （OneBotAdapter: connect reverse WS → 注册事件源）
8. ReminderScheduler（从 DB resync 任务 → 重建 APScheduler jobs）
9. AgentRuntime     （ProviderManager + ToolRegistry，M4 起）
10. API             （FastAPI + SSE，最后启动；监听地址由配置决定，默认 127.0.0.1）
```

任一环节失败：已启动组件按逆序回滚停止，进入 FAILED。

## 关闭顺序（graceful shutdown）

```
1. 停止接收新事件（EventBus.pause_publish）
2. 停止 Adapter（断开 WebSocket，等 in-flight 发送完成）
3. 停止 ReminderScheduler（APScheduler shutdown）
4. 取消/等待所有 owned background tasks（EventBus dispatch、SSE connections）
5. flush DB（提交未完成事务）
6. 关闭 Provider clients
7. 关闭 DB 连接
```

## 后台任务所有权

规则：**所有 `create_task` 必须保存引用到 owner**，owner 在 shutdown 时取消。

- EventBus dispatch task → owner: EventBus
- Adapter receive loop → owner: OneBotAdapter
- Reminder jobs → owner: Scheduler
- SSE streams → owner: FastAPI（connection scope）

禁止：fire-and-forget `create_task` 后不持有引用（shutdown 会泄漏挂起 task）。

## 失败隔离

- EventBus handler 异常：捕获并记录（trace_id + handler name），不拖垮整个 bus。
- Adapter 断线：视为可恢复，指数退避重连，日志限频。
- Provider 错误：分类（timeout/auth/rate_limit/model/network），不把原始异常堆栈抛给用户。
- 组件级隔离：任一组件 FAILED 不阻止其他组件继续运行（除非启动阶段）。

## Health

`GET /api/health`（M5 实现）返回：runtime 状态、adapter 连接状态、DB 可达性、最近事件时间戳。供 WebUI 状态页与外部监测使用。

## 配置入口

- `CAMPUSCUE_ENV`：`production`（默认）/ `dev` / `test`。test 模式下 runtime 启动时断言数据目录隔离。
- 数据目录：本地优先（如 `data/`），与代码目录分离，gitignore。
