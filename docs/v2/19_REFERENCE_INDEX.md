# 19_REFERENCE_INDEX.md

> 未来工作区 AI 的省 Token 入口：**先读本文件**，按需再打开源码。AstrBot 研究结果只维护在本文件与 03/04 文档中。
> 基准：AstrBot commit `30e20318c`；V1 commit `db35d77`；研究日期 2026-08-09。

## AstrBot 关键路径索引（相对 `astrbot/`）

| 主题 | 路径 | 关键内容 | 详见 03 文档 |
|---|---|---|---|
| Composition Root | core/initial_loader.py（57 行） | InitialLoader：建 lifecycle → init → start → gather | §1 |
| Lifecycle | core/core_lifecycle.py（480 行） | initialize() 顺序组装（L158-294）；stop() 逆序（L381-422） | §1 |
| EventBus | core/event_bus.py（83 行） | asyncio.Queue + 每事件 Task + 强引用防 GC | §2 |
| Platform 抽象 | core/platform/platform.py | run()/meta() 契约；commit_event = queue.put_nowait | §3 |
| PlatformManager | core/platform/manager.py（360 行） | 延迟 import + 注册表；_task_wrapper 状态管理 | §3 |
| 统一事件 | core/platform/astr_message_event.py | `unified_msg_origin = platform:type:session_id` | §3 |
| OneBot 接收 | core/platform/sources/aiocqhttp/aiocqhttp_platform_adapter.py（513 行） | CQHttp → on_message → convert → handle_msg → create_event → commit_event | §4 |
| OneBot 段转换 | 同上 `_convert_handle_message_event`（L198-425） | groupby 分段；reply 递归拉取；at 反查昵称；非 array 拒绝 | §4 |
| Pipeline | core/pipeline/scheduler.py + stage_order.py + process_stage/stage.py | 9 stage 注册表 + 洋葱模型 | §5 |
| Provider 抽象 | core/provider/provider.py | AbstractProvider；text_chat 统一签名 | §6 |
| ProviderManager | core/provider/manager.py（927 行） | 注册表延迟导入；get_using_provider 三级选择 | §6 |
| Provider 实体 | core/provider/entities.py | ProviderRequest（含 func_tool + tool_calls_result）；LLMResponse | §6 |
| Tool 定义 | core/agent/tool.py | ToolSchema（JSON Schema 校验）；FunctionTool；ToolSet + 三厂商 schema | §6 |
| Agent 循环 | core/agent/runners/tool_loop_agent_runner.py（1568 行） | step() 状态机；streak≥3 防重复；超时；abort 赛跑 | §7 |
| Agent 驱动 | core/astr_agent_run_util.py | run_agent：max_step 达限拔工具+强制总结 | §7 |
| 工具执行 | core/astr_agent_tool_exec.py | 四路分发；asyncio.wait_for 超时 | §7 |
| Cron | core/cron/manager.py（516 行） | APScheduler；sync_from_db 一次；add_job replace_existing；misfire_grace_time=30 | §8 |
| Dashboard 后端 | dashboard/server.py | FastAPI + Hypercorn；JWT + token-bucket 限流 | §9 |

## CampusCue V1 关键路径索引（相对仓库根，审计副本）

| 主题 | 路径 | 关键内容 | V2 关系 |
|---|---|---|---|
| 启动 | main.py | InitialLoader 启动 AstrBot core（L44-47, 228-230） | 丢弃 |
| 业务入口 | astrbot/builtin_stars/campuscue/main.py | star：群消息观察 + 工具注册 + resync 绑定（底座 4 处侵入之一） | 重写 |
| 数据模型 | campuscue/models.py | 5 张 campus_ 表；as_utc() 修 naive bug（L26-42）；CAMPUS_TIMEZONE（L18） | REUSE（schema） |
| L1 预筛 | campuscue/extractor/prefilter.py | 关键词加权打分阈值 3.0；PURE_CHATTER；0 个 astrbot import | REUSE |
| L2 LLM | campuscue/extractor/llm.py | 直连 Ark（L32）；json_object + 宽容解析；25s 超时；ARK_API_KEY env | REUSE（升级 schema 约束） |
| L3 时间 | campuscue/extractor/timeresolve.py | resolve_deadline（L205）；23:59 约定；PAST_TOLERANCE；400 天上限；**CAMPUS_TZ 不可注入（B12）** | REUSE（修时区注入） |
| 去重 | campuscue/store.py | dedup_key = sha256(umo\|标题\|deadline到分钟)（L57-75）；36h 窗口（L86-94） | REUSE（补强指纹） |
| 数据层 | campuscue/store.py | 模块级函数 + `async with db_helper.get_db()`；直接绑 AstrBot 共享 SQLite | REWRITE |
| 工具 | campuscue/tools.py | 5 个 FunctionTool（create/list/complete/set_reminder/analyze）；umo 作用域 | REWRITE（语义保留） |
| 提醒 | campuscue/reminders.py | 三档排期；crontab 钉死分钟；resync_all（L528-610）；5 道防重复防线 | REWRITE（逻辑保留） |
| 通知 | campuscue/notify.py | 推送到指定目标会话（不回源群）；PowerShell+WinRT toast | REWRITE |
| API | campuscue/api/routes.py | 路由表（完整见 02 文档 §7）；SSE 在 routes.py /stream（L668-732） | REWRITE（语义保留） |
| 校验 | campuscue/api/schemas.py | Pydantic 严格校验（umo 格式、import kind/version） | REUSE |
| 备份 | campuscue/api/backup.py | 单事务替换 5 表；排除敏感 | REUSE |
| 导入导出 | campuscue/api/transfer.py | campuscue.tasks v1；携带溯源、排除运行时字段 | REUSE |
| 接入向导 | campuscue/api/setup.py | NapCat 安装/配置/QR；读适配器私有 `_wsr_api_clients`（最深耦合） | REWRITE/FUTURE |
| 前端 | campuscue/web/src/ | 自写 Vue3 SPA；App.vue 1133 行；boardState.js 纯函数；**+8h 硬编码（B12）** | REWRITE（纯函数带） |

## 重要结论速查（已 CONFIRMED）

1. V1 = AstrBot Runtime + CampusCue Business Layer（main.py:44-47 + campuscue/__init__.py + 仓库含完整 astrbot/）。
2. V1 业务核心（L1/L3 纯逻辑、dedup、transfer/backup 格式、web 组件）与 AstrBot 几乎零耦合，可带走。
3. V1 真正耦合点：store(db_helper)、tools(FunctionTool/ContextWrapper/AstrAgentContext)、reminders(CronJobManager/Context)、setup(私有属性内省)。
4. AstrBot EventBus = asyncio.Queue + 每事件 Task + 强引用；错误隔离不杀循环。
5. OneBot 转换：groupby 分段 → text 拼 message_str；reply 递归；at 反查昵称；@bot 不进文本；非 array 拒绝。
6. AstrBot Agent：tools 为空 → DONE；达 max_step 拔工具+强制总结；工具异常以 "error: ..." 回填。
7. AstrBot Cron：APScheduler + 启动 sync_from_db 一次 + add_job(replace_existing=True, misfire_grace_time=30)。
8. V1 已验证提醒 5 道防重复防线（见 10_REMINDER.md）。
9. V1 时区：存 aware UTC，渲染 Asia/Shanghai；CAMPUS_TZ 常量 + 前端 +8h 均硬编码（B12）。
10. V1 LLM 测试缺口：extract() 从未在测试跑过（B13）。

## 重新打开源码的触发条件

- 本索引/03/04 文档信息不足
- 上游版本改变（需外部审核批准）
- 外部审核要求
- 结论出现矛盾

## 相关文档链

00（基准）→ 01（产品）→ 02（V1 审计）→ 03（AstrBot 研究）→ 04（OneBot 管线）→ 05（架构）→ 06（领域模型）→ 07（生命周期）→ 08（Provider/Agent）→ 09（存储）→ 10_TASK_PIPELINE → 10_REMINDER → 11（API）→ 12（WebUI）→ 13（Bug 教训）→ 14（安全）→ 15（测试）→ 16（迁移）→ 17（里程碑）→ 18（ADR）→ 19（本文件）
