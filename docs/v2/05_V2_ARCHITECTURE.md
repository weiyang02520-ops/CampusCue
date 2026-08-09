# 05_V2_ARCHITECTURE.md

> CampusCue V2 目标架构总览。M0 阶段为设计目标；各模块在对应 Milestone 中实现，代码存在≠验收通过。

## 模块拓扑与依赖方向

```
QQ / NapCat
   │ OneBot v11 (Reverse WebSocket — NapCat 为 CLIENT，主动拨入)
   ▼
adapters/onebot/  ◄── WebSocket SERVER（监听 127.0.0.1:6199，接受 NapCat 连接）
   │                      │
   │  帧分类：Event Frame → converter → CampusEvent；Action Response Frame → echo 关联
   │                      │
   ▼                      ▼
core/events (CampusEvent) │
   │                      │
   ▼                      │
core/bus.EventBus (有界 async queue, backpressure)
   │                      │
   ▼                      │
core/router.Router        │
   ├──► tasks/extraction (Task Pipeline)
   └──► agents/ (Agent Chat)
   │
   ▼
OutgoingMessage → dispatcher/runtime → Adapter.send()（Outbound 直连，不经 EventBus）
```

依赖方向（唯一）：`external/platform → adapters → core → services → repositories → storage(database)`。

- `agents/` 与 `tasks/extraction` 都调用 `tasks/service`（TaskService），**不**直接操作 DB。
- `api/` 路由只做 HTTP 校验 → 调 Service → 响应；业务逻辑不进 Router。
- `reminders/` 由 TaskService 驱动（任务截止变化 → 重建提醒），自身读写 reminders 表。
- **Outbound 不经过 EventBus**：Handler result / OutgoingMessage → dispatcher/runtime → `Adapter.send()`。第一版不造第二条 outbound bus（N 修正）。

## 运行时组件（CampusRuntime 管理）

| 组件 | 职责 | 生命周期 |
|---|---|---|
| Config / Secrets | 配置加载（yaml/env）+ secret_reference 解析 | 最先启动 |
| storage/database | SQLite + SQLAlchemy/SQLModel | 早启动 |
| repositories | Task/Source/Extraction/Reminder/Provider/Setting 仓储 | 依赖 DB |
| services | TaskService / ReminderService / NotificationService / ProviderService | 依赖仓储 |
| core/bus | EventBus | 可早启动 |
| adapters/onebot | OneBotAdapter（receive/send/status） | 收到新事件前启动 |
| reminders | APScheduler 实例（DB resync） | 服务就绪后启动 |
| api | FastAPI（REST + Realtime SSE） | 最后启动 |
| agents | AgentRuntime（Provider + ToolRegistry） | API 前启动 |

## 事件流（M1 范围）

```
CampusEvent(payload)
  → transport dedup（self_id, message_id）
  → bus.publish(event)（有界队列，await put → 背压）
  → Router.route(event)
      ├─ guard: valid message / self-message / duplicate / minimal rate
      ├─ TaskExtractionHandler（M2 起）
      ├─ AgentChatHandler（M4 起）
      └─ CommandHandler / SystemHandler
  → Handler result → OutgoingMessage → dispatcher → Adapter.send()（Outbound 不经 EventBus）
```

## 任务流 — progressive activation（最终流程，按 Milestone 渐进激活）

```
CampusEvent
  → SourcePolicy (L0)            [ACTIVE FROM M2]
  → Prefilter (L1 本地规则, 省 token)      [ACTIVE FROM M2]
  → ContextCollector (L2 最小上下文)       [ACTIVE FROM M2]
  → LLM Classifier/Extractor (L3 结构化 Schema 输出，走 M2 Provider Foundation) [ACTIVE FROM M2]
  → TimeNormalizer (L4 显式 timezone/current_time 注入) [ACTIVE FROM M2]
  → Deduplicator (L5 指纹组合 + explainable reason)     [ACTIVE FROM M2]
  → TaskService.create (L7)     [ACTIVE FROM M2]
  → ReminderService (L8)        [ACTIVE FROM M3]
  → Realtime 通知 (L9)          [ACTIVE FROM M5]
```

M2 不实现：Reminder（M3）、Realtime（M5）。TaskService 的提醒/通知钩子在 M2 为可选/惰性接线，不依赖假实现（与 [10_TASK_PIPELINE](10_TASK_PIPELINE.md)、[17_MILESTONES](17_MILESTONES.md)、[07_RUNTIME_LIFECYCLE](07_RUNTIME_LIFECYCLE.md) 一致）。

## Agent 流（M4 范围）

```
User Input → AgentContext(conversation + budget)
  → Provider (LLM)
  → tool_calls? → validate args → ToolRegistry.execute → ToolResult → append → LLM again (max 6-8 steps, timeout, abort)
  → Final Response
```

## Web 流（M6 范围）

```
WebUI → FastAPI (REST) → Service → Repository → SQLite
WebUI → SSE (notification only) → 断线重连 → REST refresh canonical state
```

## 关键约束（设计红线）

1. DB = 唯一业务事实源；Runtime cache / APScheduler / Pinia / SSE 均为派生。
2. 任何调用方不得绕过 Service 层直接写 DB。
3. OneBot JSON 不出 Adapter 边界。
4. 禁止 `import astrbot`（Anti-AstrBot Gate，M1 起扫描）。
5. 每轮修改：单一目标、小 diff、可回滚、可测试。
