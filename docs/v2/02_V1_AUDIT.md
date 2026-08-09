# 02_V1_AUDIT.md

> CampusCue V1 逐模块审计。证据来自 V1 仓库（commit `db35d77`）源码、PROGRESS.md 与 tests/。
> 完整审计报告（各模块逐点证据、行号、耦合评级）见本目录审计工作记录；本文件为结论版。

## V1 整体结论

**V1 = AstrBot Runtime + CampusCue Business Layer**（[CONFIRMED]）

- `main.py` 直接依赖 `astrbot.core`，用 `InitialLoader` 启动整个 AstrBot core（`main.py:44-47, 228-230`）。
- 仓库保留完整 `astrbot/`（7.1MB、476 个 py 文件）与 `dashboard/`（4.9MB）。
- `campuscue/__init__.py` 明言"sits on top of the AstrBot runtime"。
- 部分历史 Bug 修复直接修改 `astrbot/core/*`（如 `astrbot/core/log.py` 的日志压制，见 PROGRESS 第六轮）。

## V1 模块规模

- `campuscue/` 共约 8.7k 行 Python + Vue 单页看板。
- 主要模块：models 335 / extractor 约 1.5k / store 476 / tools 665 / napcat 694 / notify 381 / reminders 653 / provision 617 / api 约 2.9k / replay 280。

## V1 关键证据补充（详细审计记录摘要）

- **数据层**：5 张表全部 `campus_` 前缀（campus_tasks/campus_extractions/campus_sources/campus_profiles/campus_settings），时间约定"存 aware UTC，墙钟渲染 Asia/Shanghai"；`as_utc()` 修复 SQLite naive datetime 8 小时偏移 bug（models.py:26-42）。
- **三级管道**：prefilter 纯规则关键词加权（阈值 3.0，0 个 astrbot import）；llm 直连 Ark HTTP（**不走 ProviderManager**，`response_format: json_object` + 宽容解析兜底，未用 API 级 JSON Schema）；timeresolve 纯代码解析（"周五晚上12点"→23:59 等约定），`sent_at` 可注入但 **时区不可注入**（CAMPUS_TZ 模块常量，profile.timezone 字段存在但被忽略 → V2 必须打通）。
- **去重**：`store.dedup_key` = sha256(umo|归一化标题|deadline到分钟) + 36h 窗口查重；dismissed 任务仍算重复（防重新抽取）。
- **入口 star 在 astrbot 包内**（`astrbot/builtin_stars/campuscue/main.py`）：方向是 astrbot→campuscue；底座共 4 处侵入（star 目录、dashboard router 挂载、静态路由、log 压制）。
- **LLM 测试不 mock**：`extract()` 从未在测试里跑过；只测 `_parse_content` 私有解析。DB 用真实临时 SQLite + monkeypatch store.db_helper。
- **前端**：完全自写 Vue 3 SPA（无 router/pinia/UI 库，单运行时依赖 vue）；`boardState.js` 纯函数可单测；**前端硬编码 +8h 偏移**（boardState.js:3）——时区硬编码点，V2 需修。

## 逐模块审计结论表

| 模块 | 职责 | AstrBot 耦合强度 | V2 Action |
|---|---|---|---|
| campuscue/models.py | SQLModel 表（campus_tasks 等） | LOW（仅共享 db metadata） | REUSE_BEHAVIOR（重写独立） |
| extractor/prefilter.py | 本地规则预筛，省 token | LOW | REUSE_BEHAVIOR |
| extractor/llm.py | LLM 结构化抽取 | MEDIUM（走 AstrBot provider） | REWRITE |
| extractor/timeresolve.py | 相对时间解析 | LOW | REUSE_BEHAVIOR |
| extractor/pipeline.py | 三级管道编排 | MEDIUM（logger 等） | REWRITE（框架轻量化） |
| store.py | 数据访问层 | HIGH（`db_helper` 共享 SQLite） | REWRITE（Repository/Service） |
| tools.py | FunctionTool 实现 | HIGH（`FunctionTool`/`ContextWrapper`/`AstrAgentContext`） | REWRITE |
| napcat.py | NapCat 接入与状态 | MEDIUM（走 AstrBot platform 体系） | REWRITE（OneBotAdapter） |
| notify.py | 推送 | LOW-MEDIUM | REUSE_BEHAVIOR |
| reminders.py | APScheduler 提醒 + resync | MEDIUM（db_helper） | REUSE_BEHAVIOR（DB 事实源独立） |
| provision.py | 初始化 / 源管理 | MEDIUM | REWRITE（SourcePolicy） |
| api/ | FastAPI 路由 + SSE | MEDIUM（logger） | REUSE_BEHAVIOR（契约重审） |
| backup.py / transfer.py | 备份 / 导入导出 | LOW | REUSE_BEHAVIOR |
| replay.py | 重放 | LOW | FUTURE |
| persona.py | 人格提示词 | LOW | FUTURE（M4 时并入 Agent prompt） |
| campuscue/web/ | Vue 看板 | LOW（自写） | REWRITE（全新 IA，M6） |

## V1 历史 Bug Inventory（来自 PROGRESS.md，逐条已确认）

| # | Bug | V1 Root Cause | V1 Fix | V2 架构性预防 |
|---|---|---|---|---|
| B01 | SSE 断连日志洪水 | Python 3.12 ProactorEventLoop 在死 socket 上每次写都 warning，10 页快速开关刷数十万行，内存 4.6GB 卡死 | 捕获 `GeneratorExit/ConnectionError/OSError/RuntimeError` 退出 SSE 循环 + `log.py` 提升 asyncio 日志级别 | V2 Realtime 连接生命周期管理（cleanup、backoff、日志限频）从设计起内置（`22 Realtime Source of Truth`） |
| B02 | SSE 状态不同步 / 重连问题 | 断连后无补拉 | 前端浏览器恢复联网后主动补拉任务/来源/统计/提醒/接入状态 | V2 原则：SSE 仅通知，断线重连 REST 刷新 canonical state |
| B03 | 看板"新建"重复创建 | `routes.py POST /tasks` 只算 `dedup_key` 未查重，LLM 工具路径有查重 | API 创建前查重返回 409 + 前端 saving 防连点 | V2 TaskService 统一创建入口，去重收敛到一个实现 |
| B04 | 首次加载群竞态 | 前端加载时序 | 修复 + 4 项 Node 状态测试 | V2 WebUI 状态机 + 测试覆盖 |
| B05 | 提醒事件污染任务卡片 | SSE 提醒事件与任务事件混用 | 区分事件类型 | V2 Realtime 事件类型明确分离 |
| B06 | 乐观操作失败未回滚 | 前端乐观更新无失败处理 | 失败回滚 + 测试 | V2 WebUI 乐观更新失败回滚为标准模式 |
| B07 | 测试实例污染真实数据 | 6186 隔离实例未用独立 `ASTRBOT_ROOT`，删除/恢复测试误清真实 6185 演示数据 | 全部测试实例统一 `ASTRBOT_ROOT=/tmp/cc-test-root` | V2 测试隔离是硬性设计（`18 测试隔离`），`CAMPUSCUE_ENV=test` 断言 |
| B08 | 端口冲突 / 状态不同步 | 多实例与启动顺序 | 进程所有权校验 | V2 Runtime lifecycle 单一实例管理 |
| B09 | 对话框焦点管理缺陷 | 弹窗打开未聚焦，键盘/读屏用户停留触发按钮 | `nextTick` 聚焦 dialog 容器 | V2 WebUI 无障碍是验收项（M6 自动测试） |
| B10 | 导入 / 恢复半状态风险 | 恢复无原子性 | 单事务替换 5 表 + 失败回滚测试 | V2 迁移 / 恢复保持原子事务 |
| B11 | 模型格式错误响应泄漏 | 完整模型响应存溯源库，异常日志复制正文 | 仅存本机溯源库，日志不复制 | V2 日志脱敏为设计约束（`16 日志`） |

状态：B01-B11 均已确认；V2 预防措施见对应章节。

## V1 已实现但 V2 决定不继承的实现（架构层面）

- AstrBot `InitialLoader` / `AstrBotCoreLifecycle` 启动体系 → V2 自建 `CampusRuntime`（轻量 lifecycle）。
- AstrBot EventBus / Pipeline 通用 DSL → V2 轻量 EventBus + Router。
- AstrBot Provider/Agent/Tool 体系 → V2 最小 BaseProvider + ToolRegistry + AgentRuntime（M4）。
- AstrBot Dashboard 认证体系 → V2 本地优先，默认 loopback，LAN 需安全模型重审。
- AstrBot platform 多适配器框架 → V2 第一版仅 OneBotAdapter。

## 从 V1 保留的能力（行为级 REUSE，实现重写）

1. 三级抽取管道思想：prefilter（省 token）→ LLM 结构化 → 时间落地 + 去重。
2. 时间解析的相对表达处理（周五/今晚/月底 等）。
3. 去重思想（但 V1 dedup 细节需重审：仅靠标题相同不足，V2 用指纹组合）。
4. 提醒三档排期（提前 1 天 / 2 小时 / 截止时刻）与 DB resync 思想。
5. 备份 / 导入导出排除敏感内容（API Key、QQ 登录态、NapCat 文件）。
6. 隐私边界：日志不记录群消息正文、任务标题、推送目标（已有回归测试）。
7. WebUI 单页看板业务能力清单（任务筛选/编辑/追踪/导入导出/提醒管理）作为 V2 UI 功能参照。
