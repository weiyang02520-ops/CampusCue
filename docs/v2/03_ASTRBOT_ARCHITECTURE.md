# 03_ASTRBOT_ARCHITECTURE.md

> AstrBot 架构研究结论。基准 commit `30e20318c`，研究日期 2026-08-09。
> 所有结论标注置信度：`CONFIRMED`（直接读源码） / `INFERRED`（推断）。
> 完整调用链细节与行号见 `19_REFERENCE_INDEX.md`；本文件只保留结论与设计启示。
> 路径前缀 `B/` = `astrbot/`。

## 1. Startup / Composition Root

- `InitialLoader`（`B/core/initial_loader.py`, 57 行）职责仅为组装+拉起：建 `AstrBotCoreLifecycle` → `initialize()` → `start()` → 建 Dashboard → `asyncio.gather` 常驻。
- `AstrBotCoreLifecycle.initialize()`（`B/core/core_lifecycle.py:158-294`）是单一 Composition Root，**单线程顺序初始化，顺序即依赖顺序**：db → config → event_queue → ProviderManager → PlatformManager → ConversationManager → CronJobManager → PluginManager(含 reload) → pipeline_scheduler_mapping（按 conf_id 分片，每配置一个 PipelineScheduler）→ EventBus → platform_manager.initialize()。
- `stop()`（L381-422）逆序清理；`restart()` 用 daemon 线程做进程级重启。
- 设计启示：**CampusCue 学单一顺序 Composition Root，但只管理自己需要的组件**（不造 20 个 Manager）。

## 2. EventBus（`B/core/event_bus.py`, 83 行）

- 真身：`asyncio.Queue`；事件是 `AstrMessageEvent` 对象本身。
- `dispatch()` 循环：`queue.get()` → 查 conf 对应 scheduler → `asyncio.create_task(scheduler.execute(event))`。
- 错误隔离：每事件独立 Task，`_pending_tasks` 持引用防 GC；handler 异常仅 log，不杀循环。
- 设计启示：**CampusCue 学 asyncio.Queue + 每事件独立 Task + 强引用集合 + 异常隔离**；不做 Redis/Kafka。

## 3. Platform Adapter 边界

- `Platform` 抽象（`B/core/platform/platform.py`）只有两个契约：`run()` + `meta()`；适配器向内的唯一出口 `commit_event(event)` = `queue.put_nowait`；`create_event(message)` 包统一事件。
- `AstrBotMessage`（纯数据结构）+ `AstrMessageEvent`（运行时事件）分离。
- `unified_msg_origin = "platform:message_type:session_id"` 是跨平台统一路由键（EventBus / Provider 选择 / 会话历史全用它）。
- `PlatformManager`（`B/core/platform/manager.py`）延迟 import + 注册表（`@register_platform_adapter`），`_task_wrapper` 统一管理状态（RUNNING/STOPPED/ERROR）与异常记录。
- 设计启示：**CampusCue 第一版只做 OneBotAdapter，保持 PlatformAdapter 边界（start/stop/send/status），但不要 360 行的 Manager**。

## 4. OneBot v11 接收管线（NapCat → 内部事件）

完整调用链（CONFIRMED）：

```
NapCat → OneBot v11 Reverse WebSocket → CQHttp(use_ws_reverse=True)
→ on_message("group"/"private") 回调
→ convert_message(event)          # 按 post_type 分发
→ _convert_handle_message_event() # 消息段 → AstrBotMessage（groupby 按 type 分组）
→ handle_msg(abm)
→ create_event(message)           # 包成 AiocqhttpMessageEvent
→ commit_event(event)             # queue.put_nowait
→ EventBus.dispatch()
→ PipelineScheduler.execute()
```

要点：
- 消息段转换：text 拼 `message_str`；reply 调 `get_msg` 拉取被引用消息并**递归转换**（防嵌套）；at 反查昵称（`get_group_member_info`），@机器人本身不进文本；非 array 格式消息直接拒绝。
- 发送管线：`send_group_msg` / `send_private_msg`；At 后插空格防粘连；流式发送按中文标点分句 + 限速降级。
- 设计启示：**CampusCue 的 OneBotAdapter 只需消化 text（M1），at/reply/image 逐步加**；原始 JSON 不出 Adapter。

## 5. Pipeline

- Stage 注册表模式（`@register_stage` 全局注册表 + `STAGES_ORDER` 名称排序）。
- 9 个 stage 顺序：`WakingCheck → WhitelistCheck → SessionStatus → RateLimit → ContentSafety → PreProcess → Process → Decorate → Respond`。
- 洋葱模型：stage 若返回 AsyncGenerator，yield 前=前置处理，yield 后=后置处理，递归下钻；`event.is_stopped()` 短路。
- 设计启示：**CampusCue 不复制 Pipeline DSL**，用 Guard → Router → Handler 的直线流程。

## 6. Provider

- `AbstractProvider` 抽象出 5 类：Provider/STT/TTS/Embedding/Rerank；聊天核心 `text_chat(...)` 签名统一，各厂商适配器实现同一签名。
- `ProviderRequest` 实体把工具链路做进去：`func_tool: ToolSet` + `tool_calls_result` 回填，Provider 不感知 agent 循环。
- `LLMResponse` 含 `tools_call_name/args/ids`、`usage: TokenUsage`、`raw_completion`。
- `ProviderManager`：注册表延迟导入（`@register_provider_adapter`）+ `get_using_provider` 选择策略（per-umo 偏好 → default → 第一个）。
- 设计启示：**CampusCue 学"统一签名 + 注册表 + 请求实体承载工具链路"**；但只做 OpenAICompatible 一类，不做 5 类 provider。

## 7. Agent Tool Loop

- 工具定义模型：`ToolSchema`（name/description/parameters JSON Schema）+ `FunctionTool`（handler）；`ToolSet` 持有多家 schema 转换器（openai/anthropic/google）。
- 循环（`tool_loop_agent_runner.step()` 单步状态机，1568 行）：
  - LLM 返回空 tools_call → DONE（`_complete_with_assistant_response`）
  - 有 tools_call → `_handle_function_tools`：按 properties 过滤参数 → 未知工具报错 → 执行（`asyncio.wait_for` 超时）→ 异常以 "error: ..." 回填 → `ToolCallsResult` 追加上下文 → 下一轮 LLM
  - 终止：无 tools_call / 达 max steps（默认 30，拔工具+强制总结）/ 用户停止（abort 信号与 LLM 调用赛跑）
  - 防呆：同工具连续调用 streak≥3 逐级系统提示
- 设计启示：**CampusCue 学最小 Tool Loop**（validate → execute → append → 再 LLM），max_steps 6-8，超时/中断/错误处理必备；不学 10 种 resp.type 分发和 1568 行单文件。

## 8. Cron / Reminder（`B/core/cron/manager.py`, 516 行）

- **APScheduler（AsyncIOScheduler）+ 从 DB 恢复**（`sync_from_db()`，启动时一次，`_db_synced` 防重复）。
- 幂等：`add_job(..., id=job_id, replace_existing=True, misfire_grace_time=30)`。
- 执行前重新从 DB 读 job 拿最新状态；run_once 任务执行后删除。
- 设计启示：**CampusCue 采用相同思想：DB Reminder = Fact，APScheduler = 运行时派生，重启 resync，job_id 幂等**（见 `10_REMINDER.md`）。

## 9. Dashboard Backend（`B/dashboard/server.py`, 611 行）

- FastAPI + Hypercorn；`app.state.services` 挂 ~25 个 Service 类；legacy_router + `/api/v1` 双轨。
- JWT 中间件 + token-bucket 限流 + 自动生成 jwt_secret。
- 设计启示：**CampusCue 第一版本地优先，默认 loopback，不做整套 Auth 系统**；若开 LAN 再设计安全模型。

## 10. 值得学的设计思想（10 条）

1. 单一顺序 Composition Root，启动顺序即依赖顺序。
2. 平台边界只暴露 `run()`/`meta()` + `commit_event()`，平台差异消化在内部统一模型。
3. EventBus = asyncio.Queue + 每事件独立 Task + 强引用防 GC + 异常隔离。
4. `unified_msg_origin` 作为全局路由键统一会话/Provider/Cron 定位。
5. Stage 注册表 + 顺序表实现可扩展 pipeline 而不改核心调用链。
6. Provider 请求实体承载工具链路（func_tool + tool_calls_result 回填），Provider 不感知 agent 循环。
7. 工具定义即数据（name/description/JSON Schema/handler），schema 转换器收敛厂商差异。
8. 工具执行与 LLM 循环分离（runner 只消费 `LLMResponse.tools_call_*`）。
9. 后台任务完成用"伪事件唤醒主 agent"回流管线。
10. DB resync 思想：调度器状态全部可从 DB 重建。

## 11. 不该照搬的复杂度（10 条）

1. 上百个 `match case` 延迟导入清单（注册表应自动生成）。
2. ProviderManager 三层"当前 provider"状态 + 新旧 API 并存。
3. `AstrMessageEvent` 500+ 行单类承载六大职责。
4. 多个布尔标志互相影响的语义判定（`_force_stopped` 等）。
5. 1568 行单文件 runner 叠加大量提示词工程式分支。
6. `run_agent` 10 种 resp.type if/elif 分发。
7. 子代理完成后重建完整 MainAgent 汇报（token 放大）。
8. DB 与调度器最终一致窗口 + 直读补偿。
9. 每平台 300-500 行适配器样板（平台方言内联）。
10. Dashboard legacy + v1 双轨 API。
