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

## 2. CURRENT PROJECT TRUTH（2026-08-09 M0.1）

| 项 | 值 |
|---|---|
| 项目 | CampusCue V2（课讯）：校园事务 AI Agent 平台 |
| 当前门 | **M0 = PASS；M1 = PASS（REAL ENV VERIFIED 2026-08-10）；M2 = READY_NOT_STARTED** |
| 仓库 | weiyang02520-ops/CampusCue（public）；current HEAD 从 Git 实时获取 |
| V2 核心 | 零 AstrBot 依赖；DB 事实源；OneBotAdapter（WS SERVER）边界；TaskService 唯一入口 |
| 代码 | **v2/ 独立 root 已有 M1 实现**（src/campuscue + 87 tests）；Legacy `campuscue/`/`astrbot/`/`dashboard/` 冻结 |
| REAL ENV | 已验证：NapCat v4.18.18 + 真实 QQ hello→received:hello（私聊+群聊）+ 非 hello 不回复 + 重启自动重连 |

## 3. CURRENT MILESTONE / GATE

- 门控：每 Milestone 完成 → 真实测试 → 更新 handoff → checkpoint → push → 远程验证 → **STOP** → 外部 ChatGPT 审核 → 通过才进下一 Milestone。
- **未经外部审核禁止自动进入下一 Milestone**。
- 下一个待执行：M1（Independent QQ Runtime）——等外部审核确认后才开始。

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

- 远程验证成功后 **STOP**；报告：PASS/FAIL、完成项、验证项、仓库、commit、remote verified、当前门（如 M0 = PASS, M1 = READY_NOT_STARTED）。
- 等待外部 ChatGPT 读取 GitHub 后再继续；未经审核不自动进入下一 Milestone。

## 18. CURRENT NEXT TASK

- **当前状态**：M1 = PASS（REAL ENV VERIFIED 2026-08-10）。等待外部 ChatGPT 最终 M1 审核。
- **M2 预备（M1 PASS 确认后启动）**：Provider Foundation（BaseProvider/LLMRequest 最小集/LLMResponse/taxonomy/OpenAICompatible/最小 Manager/structured output）**独立于 Tool System**；SQLite（sources/tasks/extractions）+ Source/Extraction/Task 仓储 + SourceService/TaskService；Task Pipeline（L0-L7）；修 V1 遗留 B12（时区注入）/B13（LLM 测试缺口）。
- **运行 V2 必须用独立 venv**（repo 根有 Legacy campuscue/，import 会遮蔽）——真实环境已用 `v2/.venv-m1-real` 验证。
- 详查 docs/v2/04、17_MILESTONES（M1/M2/M4）、07、06、08、10_TASK_PIPELINE。
