# AGENT_MEMORY.md — Workspace Agent 长期执行认知

> 供新 Workspace Agent（Claude Code / Codex / DeepSeek 等）快速恢复执行能力。**读本文件 → PROJECT_STATE → HANDOFF → DECISIONS → 当前 Milestone 文档 → 必要源码。**
> 本文件保存"当前可执行真相 + 约束 + 工作流"，不保存闲聊。

---

## 1. EXECUTION BOOTSTRAP（每次接手先做）

```
1. 读本文件（AGENT_MEMORY）
2. 读 .ai-handoff/PROJECT_STATE.md（阶段事实源）
3. 读 .ai-handoff/HANDOFF.md（上一轮交接）
4. 读 .ai-handoff/DECISIONS.md（决策速查）
5. 读当前 Milestone 文档（docs/v2/17_MILESTONES + 对应子系统）
6. 只读必要源码（19_REFERENCE_INDEX 定位）
```

避免每轮重读整个仓库 / AstrBot。

## 2. CURRENT PROJECT TRUTH（Last Updated 2026-08-20 · M6.3 WebUI checkpoint）

| 项 | 值 |
|---|---|
| 项目 | CampusCue V2（课讯）：校园事务 AI Agent 平台 |
| 当前门 | **M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW；M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED** |
| 仓库 | weiyang02520-ops/CampusCue（public）；current HEAD 从 Git 实时获取 |
| V2 核心 | 零 AstrBot 依赖；DB 事实源；OneBotAdapter（WS SERVER）边界；TaskService 唯一入口 |
| 代码 | **v2/ 独立 implementation root**：M1-M4 完成；M5 FastAPI REST + SSE + schema v3；M5.1.1 route cleanup complete locally；Legacy frozen。最新本地 checkpoint 证据：**488 tests passed**（2026-08-20，fresh `.venv-m511fresh` non-editable） |
| REAL ENV | 已验证：M1.2 + M2b.2 QQ 全链路；M4.2 Real Provider Tool Call PASS；M4.3 Real QQ Agent E2E PASS；M5 本地 uvicorn HTTP smoke PASS（2026-08-19） |

## 3. CURRENT MILESTONE / GATE（Last Updated 2026-08-20 · M6.3 WebUI checkpoint）

- **门控**：每 Milestone 完成 → 真实测试 → 更新 handoff → checkpoint → push → 远程验证 → **STOP** → 外部 ChatGPT 审核 → 通过才进下一 Milestone。
- **未经外部审核禁止自动进入下一 Milestone**。
- **当前状态**：M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW；**M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。
- **下一步**：External visual comparison of M6.2.1 baseline and M6.3 evidence; M6 FINAL must not be declared from local evidence alone。
- **M3 scope note**：cross-repository Task/Reminder atomicity is a known limitation/open design risk；startup `resync_all()` recovery accepted；本 checkpoint 不重新设计 M3。
- **M4 first-version limitation**：[DESIGN_LIMITATION] M2 UNIQUE `(source_id, source_message_id)` 使同一 Agent 用户消息最多创建一个 Task；第二次 `task_create` 安全失败；无 schema v3。
- **M4.2 real provider fact**：真实 OpenAI 兼容端点（DeepSeek）tool-call 轮次可能同时返回辅助 content + tool_calls——tool_calls 权威、辅助文本丢弃（`_parse_ok` 最小修复，M4.2）。

## 4. ARCHITECTURE RULES（违反 = FAIL）

1. **零 AstrBot**：任何 `import astrbot` / `from astrbot` → Anti-AstrBot Gate FAIL。V2 在无 AstrBot 环境必须完整运行。
2. **DB = 唯一业务事实源**；runtime cache / scheduler / 前端 store / SSE 均为派生，可随时从 DB 重建。
3. **SSE 只通知**；前端断线重连 → REST 全量补拉 canonical state。
4. **OneBot JSON 不出 Adapter**：converter 纯函数转换；业务层只见 CampusEvent。
5. **TaskService 唯一创建/变更入口**：API / Agent Tool / Extraction Pipeline 全走它；dedup、提醒联动、通知收敛一处（B03 教训）。
6. **Outbound 不经 EventBus**：Handler result → dispatcher → Adapter.send()。
7. **Reminder 调度可完全由 DB 重建**：reminders 表 = 事实，APScheduler job = 派生，幂等（job_id + replace_existing）。
8. **无 Plugin System**（第一版）；Handler + ToolRegistry 够用。
9. **时区/时钟显式注入**：禁 `datetime.now()` 直用；测试固定时钟。
10. **日志脱敏**：不记录消息正文/发送者/群号/任务标题/截止/推送目标/secret；LLM 原始输出只落溯源库。
11. **OneBot Reverse WS：CampusCue 是 SERVER**，等 NapCat client 重连；**CampusCue 不 outbound 指数退避重连**（M0.2）。
12. **Memory 不维护动态 Git HEAD**：current HEAD 在 recovery 时从 Git/GitHub 获取；Memory 只记里程碑 commit 与历史基线（M0.2）。
13. **M2 Provider Foundation 不依赖 M4 Tool System**：无 ToolSet/ToolRegistry/ToolDefinition/AgentRuntime 依赖；tool-calling 字段标 M4 EXTENSION / inactive until M4（M0.2）。
14. **Pending action 上限 = backpressure（semaphore 等待），不是报错**；slot 获取→校验连接→注册→发送→清理→释放，finally 保证取消不泄漏 slot（M1.1）。
15. **bounded 配置 fail-fast**：queue_maxsize/in-flight/pending/dedup/action_timeout 均 >0（`asyncio.Queue(maxsize=0)` = unbounded）；port/path 合法（M1.1）。
16. **WS path 是 handshake contract**：process_request 校验 path + token，404/401 拒绝（M1.1）。
17. **Action response 严格校验**：`status=="ok" AND retcode==0` 才算成功（M1.1）。
18. **CampusEvent 无 OneBot 方言字段**（raw_message 已移除）；diagnostic mode 不 dump 明文（M1.1）。

## 5. DEPENDENCY DIRECTION

```
external/platform → adapters → core(events/bus/router) → services → repositories → storage(database)
```

- agents/ 与 tasks/extraction 调 TaskService，**不**直接操作 DB。
- api/ 路由只做 HTTP 校验 → Service → 响应；业务逻辑不进 Router。
- 消费方（API/Tool/Pipeline/Reminder/Adapter）不得绕过 Service 直接写表。

## 6. ASTRBOT REFERENCE BOUNDARY

- AstrBot 仅是 REFERENCE IMPLEMENTATION：允许读、搜、分析调用链、学设计思想。
- **禁止**：import、pip 依赖、启动其 runtime、复制子系统改变量名冒充自研。
- 基准固定 commit `30e20318c`；**未经外部审核不因上游更新改基准**。
- 研究结果已固化在 docs/v2/03、04、19；信息不足才重开源码。

## 7. COMMON FAILURE MODES（V1 教训速查，详细 docs/v2/13）

| 现象 | 根因 | 预防 |
|---|---|---|
| SSE 日志洪水/内存暴涨 | 死 socket 上循环写 + 无限重试 | 连接生命周期管理、日志限频、退避（M5） |
| 任务重复创建 | 多条创建路径 dedup 不一致 | TaskService 唯一入口（ADR-006） |
| 测试污染真实数据 | 测试用共享数据目录 | `CAMPUSCUE_ENV=test` 硬断言隔离（M2 起） |
| 提醒重复/残留 | 非幂等调度 | DB 事实 + resync + 幂等 job（M3） |
| 状态不同步 | SSE 当事实源 | REST 补拉 canonical state（ADR-003） |
| 时区错 | 硬编码偏移 | 显式 timezone 注入（ADR-010） |
| LLM 路径无测试 | extract() 从未被测 | Provider transport 可注入 mock（B13） |
| **文档一致性假绿** | keyword-based 检查漏跨文件语义冲突（M0.1 漏掉 05 任务流 L8/L9 与 10/17 矛盾） | **一致性检查必须比较同一概念在多个 canonical docs 中的语义，不能只搜关键词**（M0.2 教训） |
| **测试复制生产代码片段** | connection generation 测试手工模拟 half-finally，漏真实 finally 的 global pending cleanup（M1.1 finding A） | **lifecycle/race 测试必须走真实执行路径**（如真实 `_handle_connection`），禁止测试复制品（M1.1 教训） |
| **handler 内 detach 绕过并发限制** | EventBus handler create_task 后立即返回 → semaphore 被绕过 | **完整链路 bounded**：queue + in-flight handler + outbound send 都在 handler 内 await（M1.1 finding B） |
| **PII 泄漏（secret scan 干净也中招）** | M1.2 HANDOFF 经真实 NapCat 配置文件名提交完整 QQ 号；secret scan 只查高熵凭据 | **checkpoint 隐私检查区分 SECRET / PII / PUBLIC FIXTURE**：真实环境标识符（QQ 号/群号/含标识符文件名/用户路径/真实聊天内容）也要查；文档用语义脱敏（如 onebot11_<BOT_QQ_REDACTED>.json）；历史泄漏不擅自重写 Git 历史（需显式授权）（M1.3 教训） |
| **方法存在 ≠ 路径已验证** | Provider.test() 存在但缺 import（NameError）且从未被直接测试（M2a.1 finding A） | **public/acceptance 方法必须有直接路径回归测试**（真实调用链含 transport/parse），不能只靠相邻测试（M2a.1 教训） |
| **枚举未强制** | 规范 Enum 定义后 repository 仍接受任意字符串（M2a.1 finding C） | **闭集校验在 repository/domain 边界显式拒绝非法值 + DB CHECK 约束双层防御**（M2a.1 教训） |
| **schema 变更先于兼容检查** | initialize 先 create_all 再查版本，不兼容 DB 已被改写（M2a.1 finding D） | **先只读检测 → 拒绝 → 零变更**；无 schema_meta 但有用户表的 DB 拒绝认领（M2a.1 教训） |
| **HANDOFF append-only 复发** | 新 checkpoint 追加在旧 canonical 之下（M1.3 后 M2a.1 又发生） | **HANDOFF 每次 checkpoint 重写/reconcile 为单一 canonical**；旧里程碑细节进 CHANGELOG/Memory HISTORY/Git（M2a.2 教训，已两次 → 持久） |
| **PROJECT_STATE 内部腐烂** | 顶部 current_milestone 正确但 blocked/next_gate/verified 残留旧状态 | **每次 checkpoint 语义扫描 current_milestone/in_progress/blocked/verified/next_gate/review_focus** 的 stale 矛盾（M2a.2 教训） |
| **校验规则重复** | 创建规范 helper 后运行时仍保留等价 regex（M2a.2 finding A） | **每个消费方必须实际 import/调用 canonical helper**；重复等价代码 = 重复策略（M2a.2 教训） |
| **ORM 隐藏墙钟** | models 保留 datetime.now 默认（M2a.2 finding D） | **只有 SystemClock 可读真实墙钟**；storage models 时间戳 required（无默认） |
| **Fallback semantic drift** | primary Provider 路径用完整产品/安全契约，兼容 fallback 用简化 prompt 行为不同（M2b.1.2 finding B） | **primary 与 fallback 共享一个 canonical 语义 prompt 契约**；只有 transport/输出强制不同（`build_system_prompt(json_only)`）；真实 endpoint 可能大部分时间走 fallback，使 primary 测试失效 |
| **Broad process-name kill on multi-account desktop** | `taskkill /IM QQ.exe` 同时杀掉测试 bot 与用户活动个人 QQ（M2b.2 事故） | **桌面应用的用户会话 PROTECTED_BY_DEFAULT**；先建 PID/归属映射；只定向终止已证明的测试进程；永远不按进程名批量杀 |
| **Account identity guessed from config filenames** | 假定新生成的 `onebot11_<id>.json` 属于测试 bot，未确认账号角色（M2b.2 事故：误把用户大号当 bot） | **账号角色必须显式/可证明地映射后才能迁移配置**；用户主号配置绝不可改 |

## 8. EVIDENCE FIRST（置信度纪律）

- 结论必须来自：源码 / 配置 / 测试 / 运行 / Git 历史。
- 置信度标注：`[CONFIRMED]`（直接证据）/ `[HIGHLY_LIKELY]` / `[INFERRED]`（推导）/ `[UNKNOWN]`（不得补成合理答案）。
- **禁止**把 INFERRED 升级为 CONFIRMED。

## 9. BEFORE MODIFY PROTOCOL（改代码前至少）

1. 找定义 2. 找主要调用方 3. 找相关测试 4. 找配置入口 5. 判断影响范围

禁止：看到函数名 → 猜有问题 → 直接改。

## 10. SMALL DIFF / YAGNI

- 每轮：单一目标、小 diff、可回滚、可测试、有明确原因。
- 不做"以后也许需要"；未来需求写 NEXT_TASKS，不提前实现。
- 当前 Milestone 要什么只做什么；禁止顺手实现下一阶段/UI/插件系统/MCP。

## 11. TEST VERIFICATION LEVELS（不许混说）

```
UNIT VERIFIED / CONTRACT VERIFIED / INTEGRATION VERIFIED / REAL ENV VERIFIED / VISUAL REVIEWED / NOT VERIFIED
```

- Mock 成功 ≠ 真实 QQ 成功；HTTP 200 ≠ 业务正确；代码存在 ≠ 功能完成；测试多 ≠ 架构正确。
- 报告必须说明每项处于哪一级。

## 12. NO-VISION RULE

- 执行模型可能无视觉：**禁止声称看到页面/页面好看/截图正确/UI 协调/色彩漂亮**。
- 只能验证客观项：DOM、CSS、layout bounds、breakpoint、overflow、console error、network error、accessibility、interaction、截图成功生成。
- 审美结论留给外部模型：`VISUAL REVIEW REQUIRED BY EXTERNAL MODEL` 写入 REVIEW_REQUEST。
- **禁止生成图片**（AI Logo/插画/Banner/头像）；视觉依赖 CSS/Typography/Layout/SVG 库。

## 13. WEBUI NO-EMOJI RULE

- 正式 WebUI **全站禁 Emoji/颜文字**（导航/按钮/状态/标题/卡片/空态/Toast/设置项/装饰）。
- 图标统一单一 SVG 库（优先 Lucide）；禁止 Emoji + SVG 混用。
- 文案像正常软件（"AI 助手/开始/保存/任务已创建"），禁营销腔/卖萌腔/AI 模板腔。
- 禁典型 AI 网页视觉（渐变堆砌/发光紫球/机器人头像/宇宙背景/巨型 Hero/满屏玻璃拟态/彩色 KPI/过度圆角/炫技动画）。

## 14. SECURITY / SECRET RULE

- 配置只存 secret_reference（环境变量名）；真实 key 走 env / OS credential store；`.env` 永远 gitignore。
- 日志永不打印 secret；消息隐私见 14_SECURITY_PRIVACY（不送群全文、不存全文、保留策略可配）。
- Git 禁止：`.env*`、`*.pem/key`、`credentials*`、`secrets*`、真实数据库备份、QQ/NapCat 认证数据。
- checkpoint 前 secret scan 必跑；命中 → 处理后再提交。

## 15. GIT CHECKPOINT RULE

- 提交粒度：按小目标（feat:/fix:/test:/docs:/refactor:/chore:）。
- checkpoint 流程：更新 handoff → secret scan → 一致性检查 → git status/diff → commit → push → **remote verify（local HEAD == origin/main HEAD）** → 失败必须明确报告，不声称已同步。
- Push 失败不影响本地工作，记录原因。

## 16. MEMORY MAINTENANCE RULE

- 每轮结束：把本轮的 MEMORY DELTA（来自 prompt）与 AGENT_DISCOVERED_DELTA（来自工作）写入对应 Memory。
- Current Truth 更新；旧结论移入 HISTORY（旧方案/何时/为何改/替代/状态）。
- Provenance 标签：`[USER_STATED]` `[REPO_CONFIRMED]` `[EXTERNAL_REVIEW]` `[DESIGN_DECISION]` `[INFERRED]` `[UNCERTAIN]` `[REJECTED]` `[SUPERSEDED]`——不得升级。
- Source of truth 层级：代码/Git/测试 = 事实；ADR = 决策；PROJECT_STATE/HANDOFF = 短期；两个 Memory = 长期认知。

## 17. STOP RULE

- 远程验证成功后 **STOP**；报告：PASS/FAIL、完成项、验证项、仓库、commit、remote verified、当前门（**按真实当前状态报告**，如 M2 = AWAITING_EXTERNAL_REVIEW / M3 = NOT_AUTHORIZED）。
- 等待外部 ChatGPT 读取 GitHub 后再继续；未经审核不自动进入下一 Milestone。

## 18. CURRENT NEXT TASK

- **当前状态**：**M5 FINAL = PASS**；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW；**M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL = NOT YET DECLARED；M7 = NOT_AUTHORIZED。
- **M4 implementation**：[REPO_CONFIRMED] Provider-neutral Tool Calling、ToolRegistry、trusted source-scoped Task Tools、AgentRuntime、router/runtime wiring、per-thread lock、LRU thread cap、CJK ContextBudget、event timestamp prompt、peer-review regression tests、config/package changes。
- **M4.1 static hardening**：[TEST_CONFIRMED]（fresh installed-package isolation）TaskService `DEADLINE_UNSET` sentinel（省略=不变/None=清除/naive 拒绝）；Agent handler missing/disabled source gate；trusted `user_text` provenance（`source_text_reference` 非模型注入）；ContextBudget current-input single count；Provider timeout 独立性；multi-create first-version limitation documented。
- **M4.2 Real Provider Tool Call**：[TEST_CONFIRMED] **PASS**（2026-08-18）——openai_compatible / deepseek-chat / 真实 httpx transport；真实 Provider 自主发出 `task_list`（模型选择 scope=week/today）+ 自主 `task_get` → ToolRegistry → TaskService → 临时真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → 最终回答反映合成 DB 任务；改 title 后回答变化（数据驱动）；Source A/B 作用域隔离双向验证。
- **M4.2 真实兼容性修复**：[REPO_CONFIRMED] 真实 OpenAI 兼容端点（DeepSeek）tool-call 轮次同时返回辅助 content + tool_calls——原 `_parse_ok` 硬判 MALFORMED_OUTPUT；最小修复：tool_calls 权威、辅助文本丢弃（Agent loop 保持 final-text / tool-call 两种明确形状）；`test_6b_mixed_content_and_tool_calls_keeps_tool_calls` 覆盖新契约。
- **M4.3 Real QQ Agent E2E**：[REAL_ENV_CONFIRMED] **PASS**（2026-08-19）——NapCat Shell Windows Node v4.18.19 独立环境 + TEST_BOT 登录 + Reverse WS → CampusCue（127.0.0.1:6199/ws）→ 真实群消息 `@TEST_BOT 我这周有什么事情？` → @self Agent 激活 → 真实 DeepSeek 自主 `task_list` → ToolRegistry → TaskService → 真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → `send_group_msg` retcode 0 回复任务列表；通过生产 TaskService 修改任务标题后，第二次真实查询回复随 SQLite 数据变化（数据驱动）；普通不 @ 群消息不触发 Agent（无 Agent tool loop、无回复；仅 M2 AI-first extraction 判 has_task=false/skipped）。
- **M5 API + Realtime / M5.1.1 Hardening**：[TEST_CONFIRMED] **IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**（2026-08-20）——SSE overflow truly terminates active stream；early HTTP route close cleanup；heartbeat config wired；Uvicorn readiness barrier + occupied-port rollback；canonical `/api/v1/health`；neutral Adapter `connection.updated`；post-commit realtime exception isolation；full V2 **488 passed**。
- **验证（fresh installed-package isolation）**：[TEST_CONFIRMED] `.venv-m511fresh` 全新 non-editable 安装 working-tree V2 + test extras；imports resolved from fresh site-packages；M5/M5.1/M5.1.1 focused **24 passed**；full V2 **488 passed**；compileall PASS；Anti-AstrBot PASS；git diff-check PASS；Secret/PII scan PASS（测试中的 fake credentials/IDs 仅为 public fixtures）。
- **M6.2 WebUI**：[REPO_CONFIRMED][TEST_CONFIRMED] 保留 M6.1 Vue 3 + TypeScript + Vite + Router + Pinia + Lucide 八页面与真实 M5 flows；新增 token-driven quiet visual polish、teal accent、surface hierarchy、deadline/category/status detail、Sparkles brand mark、dark/mobile refinements；Playwright full 12 passed；axe 0；light evidence `.ai-handoff/visual/m62/`，dark evidence `.ai-handoff/visual/m62-dark/`；m61 baseline preserved。
- **M6.2.1 WebUI**：[REPO_CONFIRMED][TEST_CONFIRMED] Home timezone/date and action separation, mobile More sheet navigation, canonical `low|normal|high` priority, shared Chinese labels, theme icon semantics, and topbar cleanup complete；typecheck PASS；Vitest 4 passed；focused Playwright 12 passed；axe 0；new evidence `.ai-handoff/visual/m621/` + `.ai-handoff/visual/m621-dark/`；m61/m62 evidence preserved。
- **M6.3 WebUI**：[REPO_CONFIRMED][TEST_CONFIRMED] Cue Line + Cue Dot motif、section tint、page identity、structured empty states、Tasks/Agent/Calendar/Home primary pass、Messages/Connections/Providers/Settings consistency pass complete；typecheck/build PASS；Vitest 4 passed；focused Playwright 12 passed；axe 0；individual real integration PASS；evidence `.ai-handoff/visual/m63/` + `.ai-handoff/visual/m63-dark/`；m61/m62/m621 preserved。
- **M4 limitation**：[DESIGN_LIMITATION] One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged；second `task_create` safely fails；no schema v3。
- **M3 limitation**：[KNOWN_LIMITATION] Cross-repository Task/Reminder atomicity remains open design risk; startup `resync_all()` recovery accepted; no unit-of-work or Reminder architecture redesign in this checkpoint。
- **下一步**：External visual comparison of M6.2.1 baseline vs M6.3 screenshots；M6 FINAL must not be declared by this checkpoint。
- **M3 关键事实**：DB reminder facts canonical / scheduler jobs derived（resync_all 重建）；确定性 job_id `reminder:<id>`；APScheduler 3.11 实测：replace_existing 会追加→用显式 remove-then-add；shutdown 未启动调度器抛 SchedulerNotRunningError→容错；misfire_grace_time 必须 >0；quiet-hours 23-08 折叠 + 同分钟去重 + MIN_LEAD_SECONDS=60；停机错过不补发。
- **REAL ENV 关键事实**：NapCat Framework 启动建议 **stdout/stderr 重定向**（2026-08-10 本机实测前台启动触发 EPIPE，重定向后成功——本地观察，非普适规则）；`napimain.exe <QQ> <dll> <cjs>` 注入；WS client 配置在账号专用 `onebot11_<id>.json`；**用户大号受保护不可动**；测试 bot 独立小号。M4.3 使用官方 NapCat.Shell.Windows.Node v4.18.19 独立目录 `C:\Tools\NapCat\m43-clean`（不注入系统 QQ）；`NAPCAT_DISABLE_MULTI_PROCESS=1` 可绕过 worker `--no-sandbox` bad-option 路径；TEST_BOT quick login 需手Q 验证时回退二维码。
- **运行 V2 必须用独立 venv**（`v2/.venv-m1-real` 真实环境 / `.venv-m2iso` 隔离验证）。
- 详查 docs/v2/04、17_MILESTONES（M1/M2/M4）、07、06、08、10_REMINDER、10_TASK_PIPELINE。

## 9AG. M6.4 INFORMATION LAYERING CHECKPOINT（2026-08-20）

- **[REPO_CONFIRMED][CURRENT]**：`m6.3-ui-baseline` 已推送并指向 `5152bc6b5008e8c6fdf2cf28ff8040d87e416699`；M6.4 信息分层实现完成；**M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- **[DESIGN_DECISION]**：保留 M6.3 Blue + Teal、Cue Line + Cue Dot、light/dark、sidebar/mobile nav 和真实 API；按 progressive disclosure 将 primary / context / advanced 分层。Tasks/Agent/Messages 为主工作区，Calendar/Connections/Providers/Settings 做上下文与高级信息收纳；不改 backend/API/store/router/schema/business logic。
- **[TEST_CONFIRMED]**：fresh installed-package `.venv-m64fresh` full V2 **488 passed**；typecheck/build PASS；Vitest 4；focused Playwright 16；axe 0；real integration 2；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；secret/PII scan PASS；light/dark evidence `.ai-handoff/visual/m64/` + `.ai-handoff/visual/m64-dark/`。
- **[CURRENT]**：等待 External ChatGPT 视觉审核 M6.4；不得声明 M6 FINAL 或进入 M7。

- **M2a.1 运行时事实**：LLMRequest.timeout_s=None 默认（回落 provider 配置）；secret_reference 共享校验 providers/validation.py；Clock 注入 repository 时间戳；DB CHECK 约束（tasks/extractions/provider_configs）；schema 预检零变更（SchemaRefusedError）；186 tests 全绿。

- **AI-first 规则（ADR-013）**：本地规则不是语义 gate——MessageHygieneFilter 只 hard drop 高确定性垃圾；LocalSignalAnalyzer score 是 hints 绝不否决 LLM 调用（score=0 的正常消息仍进 LLM）；LLM 单次 triage+extraction（正常 1 call，schema fallback ≤2 calls）。

- **M2b.1.1 Hardening 事实（外部 PASS_WITH_FIXES 修复轮）**：secret env 缺失 → CONFIG_ERROR 0 transport；Extraction 审计带 provider_type+model（BaseProvider.model 公共属性）；model_said_none 保留 confidence/reason 不存输入 context；fallback 仅 STRUCTURED_OUTPUT_UNSUPPORTED（新错误码）；ContextCollector resize；显式年份不 auto-roll；CAMPUSCUE_ENV=test + pipeline + 无 DB_PATH → ConfigError；TaskService 无 threshold/死函数；dedup_key 唯一 helper build_dedup_key()；prompt-injection 防御纵深（消息永在 user role）。

- **M2b.1.2 Fallback 契约事实（外部最终复核修复轮）**：400 分类——STRUCTURED_OUTPUT_UNSUPPORTED 仅结构化特定证据（json_schema/response_format/structured_output 显式引用），generic "unsupported" 单独出现 → INVALID_REQUEST 不 fallback；主/回退共享单一 canonical `build_system_prompt(json_only)`（语义+安全契约相同，仅输出强制不同）；fallback user 消息 == primary（上下文/信号/时间戳/当前消息保留）；whitespace-only secret → CONFIG_ERROR 0 transport（strip 只用于判空，合法 secret 不 strip）；no-deadline 双方课程已知不同 → 不 dedup（`build_dedup_key` course 已知才入键）。
