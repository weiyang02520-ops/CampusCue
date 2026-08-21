# CHATGPT_MEMORY.md — 外部审核 AI 长期认知

> 供外部 ChatGPT 恢复跨会话认知用。**本文件是长期 Memory，不是短期工作状态。**
> 文档链：`.ai-handoff/PROJECT_STATE`（短期）→ `.ai-handoff/DECISIONS`（决策）→ docs/v2/*（设计）。
> 本文件保留"为什么"，去重去闲聊，CURRENT TRUTH 与 HISTORY 分离。

---

## 0. RECOVERY MODE（新的外部 ChatGPT 必须这样开始）

**禁止**一进来直接生成开发 prompt。先按顺序读：

1. 本文件（CHATGPT_MEMORY）
2. `.ai-handoff/PROJECT_STATE.md`
3. `.ai-handoff/HANDOFF.md`
4. `.ai-handoff/DECISIONS.md`
5. `.ai-handoff/REVIEW_REQUEST.md`
6. 当前 Milestone 文档（docs/v2/17_MILESTONES + 对应子系统文档）
7. 最新 commit / diff（`git log -3`、`git diff HEAD~1`）

然后重建 mental model，再决定下一轮任务。目标：**不依赖任何旧聊天记录**。

---

## 1. CURRENT TRUTH（Last Updated 2026-08-21 · M6 Final Closure Candidate）

| 项 | 值 | Provenance |
|---|---|---|
| 项目 | CampusCue V2（课讯）——校园事务 AI Agent 平台 | [USER_STATED] |
| 当前 Milestone | **M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已完成 M6.1 修复）；M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS；M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW；M6.5.3 DARK STAGE 1 = PASS；M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW；NEUMORPHISM MATERIAL = PASS；M6.5.4.1 THEME UX = PASS；GLASS FINAL = AWAITING_EXTERNAL_FINAL_REVIEW；DARK FINAL = AWAITING_EXTERNAL_FINAL_REVIEW；NEUMORPHISM FINAL = AWAITING_EXTERNAL_FINAL_REVIEW；M6 FINAL = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW；M7 = NOT_AUTHORIZED** | [REPO_CONFIRMED][CURRENT] |
| M1 结论 | 独立 QQ Runtime 实现（M1）+ correctness 8 项修复（M1.1）+ 真实 QQ/NapCat 验证（M1.2）全部 PASS；**真实 QQ hello→received:hello 已在 2026-08-10 验证** | [EXTERNAL_REVIEW] |
| V2 代码根 | `v2/`（v2/src/campuscue，独立 implementation root，ADR-011） | [REPO_CONFIRMED] |
| Legacy | `campuscue/` / `astrbot/` / `dashboard/` = reference/frozen（不改） | [REPO_CONFIRMED] |
| V2 立项原因 | V1 = AstrBot Runtime + CampusCue 业务层（main.py:44-47 InitialLoader；astrbot/ 完整目录；底座 4 处侵入）；V2 零 AstrBot 依赖 | [REPO_CONFIRMED] |
| V1 仓库 | weiyang02520-ops/CampusCue @ `db35d77`（单 commit 发布，public） | [REPO_CONFIRMED] |
| AstrBot 基准 | commit `30e20318c`（本地副本已 checkout） | [EXTERNAL_REVIEW 固定] |
| V2 仓库 | 同 V1 仓库；**current remote HEAD：RESOLVE FROM GIT/GITHUB AT RECOVERY TIME（不维护为长期 Memory 字段）** | [REPO_CONFIRMED] + [EXTERNAL_REVIEW] |
| 双 Memory | docs/context/CHATGPT_MEMORY.md + AGENT_MEMORY.md | [DESIGN_DECISION] |

## 2. GLOBAL WORKING MODE（长期 AI 协作模式）[USER_STATED][GLOBAL_WORKFLOW][CURRENT]

```

User
→ External ChatGPT（规划/审核/下一轮 prompt）
→ Workspace Agent（源码检查/实现/测试）
→ Memory 更新 → checkpoint → commit → push GitHub → remote verify
→ STOP
→ External ChatGPT 读取实际 GitHub → 独立审核 → 下一轮 prompt
```

- **GitHub = 跨模型共享事实源**。聊天记录不是事实源。
- 用户不希望每次重新解释背景。
- 长期项目默认使用该模式，除非用户明确要求不用。
- 用户反馈：该接力方式效果很好，**计划未来用于其他长期项目**。

## 3. USER INTENT

- 做自己的校园事务产品（不依赖 AstrBot 底座），第一核心是事务管理，不是聊天机器人。
- 长期工程：可跨模型、跨会话、跨时间继续；每轮独立可审核。
- 重视证据链：GitHub 上任何 AI 都能接手。

## 4. USER DECISION MODEL

- 小改动、单一目标、可回滚、可测试（总根提示词规则 4）。
- 证据优先（Evidence First）：源码/配置/测试/运行 → 结论，禁止凭经验猜（规则 1）。
- YAGNI + KISS：不做"以后也许需要"（规则 5/6）。
- 失败禁止连环乱改：先记录现象/复现/错误/影响/候选原因，再定位（规则 8）。
- 需要暂停询问的只有：核心需求冲突、删用户数据、真实账号/密钥、不可逆操作、改变产品定位、改变仓库可见性、高风险隐私（规则 13）。普通工程决策自行判断并记录理由。

## 5. PRODUCT INTENT

- 面向大学生的校园事务 AI Agent 平台。三大核心按序：**校园事务管理 → AI 助手 → QQ 自动信息入口**。
- 典型场景：QQ 群"高数第三章作业周五晚上12点前交学习通" → 自动变任务（类型/课程/标题/截止/提交方式/来源/原始消息引用）→ 提醒 → WebUI。
- AI 助手必须真实 Tool Call（task_list）访问真实数据，不能硬编码。

## 6. PRODUCT TASTE（重要，审核 UI 时使用）

- 学生每天用的工具：信息、任务、截止、来源、状态、日历、消息是重点，不是"AI 感"。
- **禁 Emoji**（导航/按钮/状态/标题/卡片/空态/Toast/设置项全部禁）；图标统一单一 SVG 库（Lucide）。
- 禁营销腔/卖萌腔/AI 模板腔（"智能""赋能""AI 驱动"）。
- 禁典型 AI 网页视觉：到处渐变、发光紫球、AI 机器人头像、宇宙背景、巨型 Hero、满屏玻璃拟态、无意义彩色 KPI、每卡不同色、过度圆角、炫技动画。
- 本地优先、隐私优先、默认 loopback。

## 7. ARCHITECTURE INTENT（核心 ADR，详细见 docs/v2/18 + adr/）

1. **Zero AstrBot**：`import astrbot` → FAIL。AstrBot 仅 REFERENCE。
2. **DB = 唯一业务事实源**；runtime cache / APScheduler / Pinia / SSE 全是派生。
3. **SSE/Realtime 只是通知传输**，不是状态源；断线 REST 补拉。
4. **OneBot 协议不泄漏进 Domain**：converter 边界；NapCat 是 Reverse WS **CLIENT**，CampusCue 是 **SERVER**（M0.1 修正）。
5. **TaskService 唯一创建/变更入口**（API/Tool/Pipeline 全走它）——V1 B03 教训。
6. **Reminder 调度可完全由 DB 重建**（DB 事实 + APScheduler 派生 + 幂等）。
7. **Provider 请求实体承载工具链路**；Provider 不感知 Agent 循环。
8. **第一版无 Plugin System**；本地优先，LAN 需重设计安全模型。
9. **时区显式注入，前端不硬编码偏移**（V1 B12 教训）。
10. **Outbound 不经 EventBus**：Handler → dispatcher → Adapter.send()（M0.1 修正 N）。

## 8. PROJECT HISTORY（压缩版）

- V1（2026-07~08）：AstrBot fork + campuscue/ 业务层（8.7k 行）。七轮修复：SSE 日志洪水（B01）、状态不同步（B02）、重复创建（B03）、测试污染数据（B07）等，399 tests passed。**业务核心（L1/L3/dedup/backup/web 纯函数）与 AstrBot 零耦合**。
- V2 M0（2026-08-09）：AstrBot 9 条链路研究（30e20318c）+ V1 全量审计 + 20 份设计文档 + 10 份 ADR。commit `6480ad2`。
- V2 M0.1（2026-08-09）：外部审核 → 修正文档精度（llm 耦合、stop 顺序、Platform 契约、Reverse WS 所有权、帧关联、有界队列、transport dedup、Guard 范围、Provider 前移 M2、M2 仓储、删消息页验收、阶段激活、Outbound 直连）+ 建立双 Memory。commit `3d70da1`。
- V2 M0.2（2026-08-09）：外部复核发现 4 个残留一致性问题 → 修正（07 断线 server 语义、05 任务流渐进激活标注、Memory 动态 HEAD 反模式、Provider Foundation 与 Tool System 解耦）+ 新增 4 条 MEMORY DELTA（见 §10A）。

## 9A. MEMORY DELTA（M0.2 新增）

- **[EXTERNAL_REVIEW][CORRECTION]**：文档级 consistency scan 报告通过 ≠ 语义一致。M0.1 的 keyword-based 检查漏掉了跨文件语义冲突（05 任务流含 L8/L9 与 10/17 矛盾）。**以后 consistency check 不能只靠关键词存在性或单文件检查，必须比较同一概念在多个 canonical docs 中的语义是否一致。**
- **[EXTERNAL_REVIEW][DESIGN_DECISION]**：**Long-term Memory 不维护动态 Git HEAD**。Current HEAD 必须在 recovery 时直接从 Git/GitHub 获取；Memory 只记录重要 milestone commits / historical baselines / contextual meaning。原因：动态 HEAD 在写 Memory 的同一次 commit 后即可过期。Git/GitHub = current HEAD source of truth；Memory = historically important milestones / context。
- **[EXTERNAL_REVIEW][CORRECTION]**：OneBot Reverse WS：CampusCue server 等待 NapCat client reconnect；**CampusCue 不进行 outbound exponential reconnect**。
- **[EXTERNAL_REVIEW][CORRECTION]**：**M2 Provider Foundation 不依赖 M4 Tool System**（无 ToolSet/ToolRegistry/ToolDefinition/AgentRuntime 依赖）；tool-calling 能力标注 M4 EXTENSION / inactive until M4。

## 9B. MEMORY DELTA（M1 新增）

- **[EXTERNAL_REVIEW][CURRENT]**：M0 / M0.1 / M0.2 最终外部审核完成。**M0 FINAL = PASS。M1 = AUTHORIZED_TO_START**（2026-08-09）。
- **[DESIGN_DECISION][CURRENT]**：**CampusCue V2 implementation 与 Legacy V1 物理隔离**（ADR-011）：V2 源码在独立 `v2/` implementation root（`v2/src/campuscue/`），Legacy `campuscue/`/`astrbot/`/`dashboard/` 冻结为 reference。V2 package 必须可独立安装/测试（fresh venv 验证）。
- **[DESIGN_DECISION][CURRENT]**：**EventBus backpressure 不仅限队列还限 in-flight handler 并发**（queue maxsize + semaphore）；否则 dispatch 无限 create_task 仍会造成内存无界增长。
- **[DESIGN_DECISION][CURRENT]**：**M1 transport dedup canonical enforcement point = OneBot Adapter ingress**（converter 后、bus.publish 前）；Router 不再次调用同一 stateful deduper。
- **[DESIGN_DECISION][CURRENT]**：**M1 EchoHandler 只响应明确测试触发 `hello`**（trimmed text 全等），不是全消息复读器；真实群消息不回复。
- **[EXTERNAL_REVIEW][SECURITY_CORRECTION]**：**Normal runtime logs 不记录完整 QQ ID/群号/消息正文**；M1 真实验收需观察这些字段时必须使用 explicit diagnostic mode（`CAMPUSCUE_DIAGNOSTIC=1`，默认 OFF，真实 ID 不得 commit，token 永不打印）。
- **[EXTERNAL_REVIEW][CURRENT]**：**M1 PASS 仍需要真实 QQ/NapCat 验证**；Fake WebSocket integration ≠ REAL ENV VERIFIED。本机无 NapCat → M1 = IMPLEMENTED_AWAITING_REAL_ENV。

## 9C. MEMORY DELTA（M1.1 新增）

- **[EXTERNAL_REVIEW][CORRECTION]**：M1 首轮外部源码审核发现：connection generation 测试只模拟了部分 cleanup，遗漏真实 finally 中 global pending cleanup。**长期教训：测试不得复制/模拟生产实现的一小段然后据此宣称真实路径 VERIFIED；对于 lifecycle/race 问题应尽量覆盖真实执行路径**（新回归测试走真实 `_handle_connection` 生命周期）。
- **[EXTERNAL_REVIEW][CORRECTION]**：**Bounded EventBus ≠ 完整 pipeline bounded**。若 EventBus handler 内 detach create_task 并立即返回，handler semaphore 可被绕过。完整链路必须检查：queue bound / handler bound / outbound bound / pending action bound。M1.1：outbound send 移入 handler 内 `await`（KISS，不造 OutboundBus）。
- **[EXTERNAL_REVIEW][CORRECTION]**：**M1 pending action capacity 使用 backpressure（semaphore 等待），不是达到上限后立即失败**。
- **[EXTERNAL_REVIEW][CORRECTION]**：**所有 bounded 配置必须 fail-fast 拒绝 0/负值**；`asyncio.Queue(maxsize=0)` = unbounded，会静默破坏 bounded 设计。
- **[EXTERNAL_REVIEW][CORRECTION]**：**OneBot configured WebSocket path 是实际 handshake contract**（process_request 校验），不是日志装饰。
- **[EXTERNAL_REVIEW][CORRECTION]**：**OneBot action response success 必须严格验证**：`status == "ok" AND retcode == 0`，缺字段视为 malformed/failed。
- **[EXTERNAL_REVIEW][SECURITY]**：不为验收无必要扩大 QQ/message 明文 diagnostic logging；真实 QQ 收到 expected response 本身就是 M1 E2E 证据（diagnostic mode 仅 verbose debug，不 dump 明文）。
- **[EXTERNAL_REVIEW][CORRECTION]**：CampusEvent 移除 OneBot-specific `raw_message` metadata（无用途、扩大隐私面、dialect 泄漏进 Domain；YAGNI）。

## 9D. MEMORY DELTA（M1.2 REAL ENV 新增）

- **[REAL_ENV_CONFIRMED]**：**M1 真实 QQ/NapCat 验证通过**（2026-08-10）：
  - NapCat `v4.18.18`（官方 Framework 注入式，`C:\Tools\NapCat\`）
  - Reverse WS：NapCat client → CampusCue server（127.0.0.1:6199/ws）**CONNECTED**
  - token 握手真实验证（NapCat 带 token 连接成功）
  - `messagePostFormat=array` 真实兼容（converter 处理真实 NapCat payload 正确）
  - 真实私聊 + 群聊 `hello` → `received: hello`（action `send_private_msg`/`send_group_msg` + `retcode 0` 响应）
  - 非 hello 消息不回复（EchoHandler 非复读机，机器侧证据：收到消息但 0 个 send action）
  - reconnect 真实验证（CampusCue 重启 → NapCat 5s 内自动重连 → hello 仍回复）
- **[REPO_CONFIRMED]**：NapCat 官方 WebSocket Client 配置 `messagePostFormat` 默认值为 array（此前 UNVERIFIED_HYPOTHESIS 升级）；但真实配置仍显式设置 array，不依赖动态默认值。
- **[REPO_FACT][CONFIG_FACT]**：NapCat Framework 版配置文件位置：`<NapCat目录>/config/onebot11_<QQ号>.json`（QQ 登录后生成）；`napcat.json` 为框架配置。
- **[OPERATIONAL_RULE]**：同一 repository 根有 Legacy `campuscue/`，V2 必须用独立 venv（`v2/.venv-m1-real`）运行，确认 `campuscue.__file__` 指向 `v2/src`。
- **[REPO_FACT]**：真实 NapCat 默认连接是 `WebSocket Client`（反向 WS 拨入），不是 WebSocket Server——与架构一致。
- **[USER_CONFIRMED][REAL_ENV]**：用户实际看到 QQ 中收到 `received: hello`（含重启后再次确认）。

## 9E. MEMORY DELTA（M1.3 新增）

- **[EXTERNAL_REVIEW][CURRENT]**：**M1 技术最终审核 = PASS**。实现（M1）+ correctness（M1.1）+ REAL ENV Gate（M1.2）全部确认。M1.3 = 连续性/隐私清理，M2 待 M1.3 外部确认后才授权。
- **[EXTERNAL_REVIEW][PRIVACY_CORRECTION]**：M1.2 HANDOFF 曾通过真实 NapCat 配置文件名意外提交完整 QQ 标识符。**当前树文档必须语义脱敏；secret scan 不足以覆盖 PII**——隐私检查必须包含真实环境标识符（QQ 号/群号/含标识符文件名/用户路径），而不只是凭据/高熵 secret。
- **[EXTERNAL_REVIEW][WORKFLOW_CORRECTION]**：**Memory CURRENT TRUTH 必须在每个 milestone 转换时更新**。只追加 MEMORY DELTA 而顶部 CURRENT TRUTH 过时 = Memory Rot。
- **[EXTERNAL_REVIEW][WORKFLOW_CORRECTION]**：**HANDOFF 是当前操作状态，不是 append-only 永久历史**。历史细节属于 Git / CHANGELOG / Memory HISTORY。
- **[EXTERNAL_REVIEW][RUNBOOK_CORRECTION]**：**发现的真实环境 workaround 只有在实际写进 runbook 才算已记录**。M1.2 发现的 Git Bash MSYS `/ws` 路径转换 → v2/README 必须含真实 workaround（MSYS_NO_PATHCONV=1 或推荐 PowerShell/cmd）。

## 9. REJECTED / SUPERSEDED APPROACHES

| 旧方案 | 何时 | 为何改 | 替代 |
|---|---|---|---|
| V1 跑 AstrBot Runtime | V2 立项 | 独立性/可控性/可维护性根本问题 | 零依赖自研（ADR-004） |
| llm.py 直连厂商 HTTP（绕过 Provider） | M0.1 | 业务层裸写厂商协议不可维护 | M2 Provider Foundation（REWRITE_INTEGRATION） |
| stop() "严格逆序清理" 表述 | M0.1 | 与 30e20318c 实际不符（显式有序 cleanup） | 显式有序 lifecycle-owned cleanup |
| Platform "只有 run/meta 两个契约" 表述 | M0.1 | 基类还有 terminate/send_by_session/commit_event 等 | 学 adapter lifecycle + 出入站边界 |
| "向 NapCat 指数退避重连"（client 思维） | M0.1 | 方向搞反：NapCat 是 Reverse WS client | CampusCue 是 WS server，等 NapCat 重连 |
| M2 验收"消息页可见" | M0.1 | API=M5、WebUI=M6 | M2 验收 = DB 断言（source/extraction/task row） |
| Provider 在 M4 才实现 | M0.1 | M2 Task Pipeline 的 LLM 需要它（依赖冲突） | Provider Foundation 前移至 M2；M4 只加 Tool/Agent |
| Guard 依赖 source-enabled | M0.1 | M1 无 SourceRepository/Service | M1 Guard 只做 valid/self/duplicate/rate |
| Response "经 EventBus 回 Adapter" | M0.1 | 无第二条 outbound bus 的设计 | Outbound 直连 dispatcher → Adapter.send() |

## 10. IMPORTANT REVIEW FINDINGS（外部审核结论，M0 轮）

- **PASS**：总体架构方向（轻量 EventBus/Router、OneBotAdapter 边界、TaskService 唯一入口、无 Plugin、DB 事实源）。
- **CHANGES_REQUESTED**（已修复，见上表）：文档精度 + Milestone dependency。
- 教训：**文档必须与源码事实严格一致**；任何"听起来合理"的绝对化表述都会被独立审核抓到。

## 11. AI ROLE MODEL

- External ChatGPT = 架构师 + 审核者 + 下一轮任务生成者。
- Workspace Agent = 执行者（证据 → 实现 → 测试 → 文档 → 提交 → STOP）。
- 双方只通过 GitHub + Memory 沟通。不越权：Agent 不评审自己，ChatGPT 不实现。

## 12. TOKEN / CONTEXT STRATEGY

- **M0 后 AstrBot 研究结果压缩到 docs/v2/03、04、19**；后续优先读自家文档，只有 Reference 不足/上游变更/外部要求/矛盾时才重开 AstrBot 源码（总根提示词 45）。
- **Memory 允许长**（用户接受）：目标是 high-fidelity recovery，不是省 token；禁止重复同一规则（长≠重复）。
- Memory 面向 AI，不要求用户可读性；dense structured Markdown + provenance 标签。

## 13. MEMORY PROTOCOL

- 每轮正式 prompt = Memory Input。Agent 抽取 **MEMORY DELTA**（分类：NEW_FACT / NEW_USER_INTENT / NEW_USER_PREFERENCE / NEW_DESIGN_DECISION / CORRECTION / SUPERSEDED / REJECTED / OPEN_QUESTION / EXTERNAL_REVIEW_FINDING）。
- prompt 自带 MEMORY DELTA 时：优先按其语义更新，不得擅自改变意图。
- Agent 工作发现 = **AGENT_DISCOVERED_DELTA**（写 HANDOFF，不直接提升为长期用户意图；外部 ChatGPT 审核后决定是否进 Current Truth）。
- **Provenance 标签**（严禁升级）：`[USER_STATED]` `[REPO_CONFIRMED]` `[EXTERNAL_REVIEW]` `[DESIGN_DECISION]` `[INFERRED]` `[UNCERTAIN]` `[REJECTED]` `[SUPERSEDED]`。
- **CURRENT TRUTH vs HISTORY**：旧结论被推翻时 Current 更新、History 记录（旧方案/何时/为何改/替代/状态），防 Memory 腐烂。
- Source of truth 层级（不得混淆）：代码/Git/测试 = 客观事实；DECISIONS/ADR = 正式设计决定；PROJECT_STATE/HANDOFF = 短期工作状态；本文件/AGENT_MEMORY = 长期认知。

## 14. CURRENT CAMPUSCUE STATE（M1.3，Last Updated 2026-08-10）

- **M0 = PASS；M1 = PASS**（实现 + correctness + REAL ENV 全部技术审核通过）
- **M1.3** = 本轮连续性/隐私清理，AWAITING_EXTERNAL_REVIEW
- **M2 = READY_NOT_STARTED / NOT_AUTHORIZED**（等 M1.3 外部确认）
- 仓库 HEAD：**RESOLVE FROM GIT/GITHUB AT RECOVERY TIME**（动态 HEAD 不维护为长期 Memory 字段）。历史 checkpoint：M0 `6480ad2`、M0.1 `3d70da1`、M0.2 `2014a78`、M1 `9bfb018`、M1.1 `71f7f99`、M1.2 `7ae0810`
- 已验证：真实 QQ/NapCat（NapCat v4.18.18，hello→received:hello 私聊+群聊、非 hello 无回复、重启自动重连）
- 未验证：无视觉（M6）；B12/B13（M2 修）
- 隐私备注：M1.2 HANDOFF 曾含真实 QQ 标识符 → 当前 HEAD 已脱敏；历史提交未重写（需显式授权）

## 15. OPEN QUESTIONS

- 无阻塞性问题。M2 等待 M1.3 外部确认。

## 16. HISTORY / TIMELINE

| 日期 | 事件 | commit |
|---|---|---|
| 2026-08-03 | V1 七轮修复完成（399 tests） | —（交付包） |
| 2026-08-09 | V1 发布 public 仓库 | `db35d77` |
| 2026-08-09 | V2 M0：研究+审计+设计文档 | `6480ad2` |
| 2026-08-09 | V2 M0.1：外部审核修复 + 双 Memory | `3d70da1` |
| 2026-08-09 | V2 M0.2：最终一致性修复（4 项）+ Memory 语义规则 | `2014a78` |
| 2026-08-09 | V2 M1：独立 QQ Runtime（v2/ 实现 + 65 tests + fake NapCat 全链路；真实 NapCat 待联调） | 本轮 |
| 2026-08-09 | V2 M0.1：外部审核修复 + 双 Memory | 本轮 |

## 9F. MEMORY DELTA（M2a 新增）

- **[EXTERNAL_REVIEW][CURRENT]**：M1.3 外部审核 = PASS。M0/M1 全部关闭。**M2 AUTHORIZED**，拆分为 M2a（Data+Provider Foundation）/ M2b（Task Pipeline + 真实 Provider + 真实 QQ 验收）；M2b 不得在 M2a 外部审核前开始。
- **[EXTERNAL_REVIEW][DOMAIN_DECISION]**：TaskStatus 规范值：`pending_confirm` / `pending` / `done` / `dismissed`（解决 06 与 10 的矛盾；单一枚举）。
- **[EXTERNAL_REVIEW][ARCHITECTURE_DECISION]**：L2 上下文 = 有界临时内存 ring buffer（message_id/timestamp/text），不建 messages 表；DB 仍是事实源；重启丢失可接受。
- **[EXTERNAL_REVIEW][PROVIDER_DECISION]**：M2 Provider 默认语义 = 恰好一个 enabled（0→NoProviderConfiguredError；>1→AmbiguousDefaultProviderError；不静默选第一行）。
- **[EXTERNAL_REVIEW][SECURITY_DECISION]**：ProviderConfig 只存 secret_reference（环境变量名）；secret 值永不进 DB/Git/日志/Memory/Handoff。
- **[EXTERNAL_REVIEW][CORRECTION]**：milestone commit 进入 HISTORY 后记录实际 commit 或指向 Git，不留 stale "pending" 措辞。
- **[REPO_CONFIRMED]**：M2a 实现（SQLAlchemy 2.x + aiosqlite + httpx）：sources/tasks/extractions/provider_configs/schema_meta 表；Source/Task/Extraction/ProviderConfig Repository；SourceService；providers/（base/models/errors/openai_compatible/manager）+ scripts/m2_configure_provider.py（临时 bootstrap，M5 替换）。

## 9G. MEMORY DELTA（M2a.1 新增）

- **[EXTERNAL_REVIEW][CORRECTION]**：Provider.test 存在但未被测试且缺 import（NameError）。**方法存在 + 相邻测试 ≠ 真实调用路径已验证**；public/acceptance 方法需要直接路径测试。
- **[EXTERNAL_REVIEW][CORRECTION]**：LLMRequest 字段是契约不是文档装饰；request 级 timeout 必须真正影响传输或删除。
- **[EXTERNAL_REVIEW][CORRECTION]**：规范枚举不是"能存合法值"就算强制；闭集域规则需要显式非法值拒绝（repository 边界 + DB CHECK 双层）。
- **[EXTERNAL_REVIEW][STORAGE_SAFETY]**：schema 兼容性必须先于任何 DB 变更检查；不兼容/未来/未知 DB：检测 → 拒绝 → **零变更**。无 schema_meta 但有用户表的 DB 拒绝认领（迁移明确要求）。
- **[EXTERNAL_REVIEW][CORRECTION]**：Clock 抽象只有在持久化/服务时间戳路径真正使用它才有用；不要造生产代码绕过的架构抽象。Repository 现在显式从 clock.utcnow() 取时间戳。
- **[EXTERNAL_REVIEW][SECURITY]**：secret_reference 必须在持久化前校验（不只首次网络请求）；配置与 Provider 运行时共享同一校验规则（providers/validation.py）。
- **[REPO_CONFIRMED]**：M2a.1 修复全部落地（186 tests 全绿）：timeout 契约生效、枚举 CHECK 约束、schema 零变更拒绝、Clock 注入、get_by_id、严格成功解析、状态码先于 body 分类。

## 9H. MEMORY DELTA（M2a.2 新增）

- **[EXTERNAL_REVIEW][CORRECTION]**：创建规范校验 helper ≠ 规则已共享；每个运行时/配置消费方必须实际使用它。重复的等价 regex/代码仍是重复策略。
- **[EXTERNAL_REVIEW][CORRECTION]**：Provider 配置数值约束必须在持久化前强制；单独测试 helper 不证明真实配置路径拒绝非法值。
- **[EXTERNAL_REVIEW][CORRECTION]**：per-request Provider override 必须在传输前满足相同契约；请求字段不能绕过 ProviderConfig 校验。
- **[EXTERNAL_REVIEW][CLOCK_RULE]**：只有 SystemClock 可读真实墙钟（M2 业务时间戳）；ORM storage models 不得含 datetime.now 回退默认。
- **[EXTERNAL_REVIEW][WORKFLOW_FAILURE]**：HANDOFF append-only 复发（M2a.1 又一次）——HANDOFF 是 canonical 当前操作状态，必须 reconcile 不能无限追加。
- **[EXTERNAL_REVIEW][WORKFLOW_FAILURE]**：PROJECT_STATE 顶部正确但内部可腐烂——每次 checkpoint 必须语义扫描 current_milestone/in_progress/blocked/verified/next_gate/review_focus 的 stale 矛盾。
- **[REPO_CONFIRMED]**：M2a.2 落地（203 tests 全绿）：validation.py 单一规则（secret/numeric/request）、ORM 无墙钟、fresh venv 隔离 PASS。

## 9I. MEMORY DELTA（M2b.1 新增）

- **[EXTERNAL_REVIEW][CURRENT]**：M2a/M2a.1/M2a.2 最终外部审核 = PASS，M2a CLOSED；M2b AUTHORIZED，拆 M2b.1（Task Pipeline + Mock Provider + SQLite）/ M2b.2（真实 Provider + 真实 QQ 验收）。
- **[EXTERNAL_REVIEW][PRIVACY_DECISION]**：L0/L1 拒绝的 QQ 闲聊不创建 Extraction 行——只有过 L1 的候选进入持久化抽取审计（避免 SQLite 变隐式聊天历史）。
- **[EXTERNAL_REVIEW][CONTEXT_DECISION]**：ContextCollector 观察启用来源的 bounded 消息（即使 L1 拒绝），因为可能消歧后续候选；仅临时内存。
- **[EXTERNAL_REVIEW][DEDUP_DECISION]**：语义去重 source-scoped + 36h；dismissed 近期任务仍算重复；exact source_message_id 最强。
- **[EXTERNAL_REVIEW][TIME_DECISION]**：自然语言截止解析锚定 CampusEvent.timestamp；持久化/去重用注入 Clock；两钟不混淆。
- **[EXTERNAL_REVIEW][DOMAIN_LIMITATION]**：Task 无专属 submission_method 列；M2b.1 存于 Extraction audit/normalized + Task.description，不做 schema 迁移。
- **[REPO_CONFIRMED]**：M2b.1 实现（256 tests 全绿）：tasks 包（L0-L7）+ TaskService 唯一边界 + 并发去重安全；Windows 平台依赖 tzdata（zoneinfo）。

## 9J. MEMORY DELTA（M2b.1 AI-first 重写）

- **[USER_STATED][PRODUCT_DECISION][CURRENT]**：CampusCue 第一版优先减少漏掉真实校园事务，而不是极限节省 LLM Token。enabled + auto_extract Source 的大部分正常自然语言消息原则上交给大模型理解。
- **[USER_STATED][ARCHITECTURE_DECISION][CURRENT]**：本地规则不负责主要语义裁决；职责 = 明确垃圾过滤 / 辅助信号 / 确定性验证 / 时间解析 / 去重 / 安全兜底。
- **[SUPERSEDED]**：旧 M2 设计"LocalPrefilter score below threshold → skip LLM"已被推翻，不能作为 CURRENT 行为（ADR-013）。
- **[DESIGN_DECISION][CURRENT]**：LLM 单次调用同时完成 task triage + structured extraction；禁止正常路径先分类再抽取两次。
- **[PRIVACY_DECISION][CURRENT]**：AI-first 使更多群消息进 Provider → 不持久化完整群历史；model_said_none 审计不保存完整输入 context；只有创建 Task 才持久化 source_text_reference。
- **[DESIGN_DECISION][CURRENT]**：LocalSignalAnalyzer 产生 hints，signal score 不能拥有 semantic veto。
- **[REPO_CONFIRMED]**：M2b.1 AI-first 落地（264 tests 全绿）：MessageHygieneFilter + LocalSignalAnalyzer + 单次调用 extractor + ≤2 calls 硬上限 + 模糊上下文测试。

## 9K. MEMORY DELTA（M2b.1.1 Real-Gate Hardening）

- **[EXTERNAL_REVIEW][CURRENT]**：M2b.1 AI-first 产品方向与主 pipeline 架构被接受。M2b.2 前需要一轮最终 real-gate hardening（已由本轮完成）。
- **[EXTERNAL_REVIEW][PROVIDER_RULE]**：配置了 secret_reference 但其环境变量缺失 → 必须在 transport 前本地失败（`ProviderError(CONFIG_ERROR)`，0 transport calls）。禁止静默发出未认证 HTTP；不打印 secret 值；不把本地配置错误转成远程 401。
- **[EXTERNAL_REVIEW][AUDIT_RULE]**：每次实际 LLM extraction 尝试应记录安全 provider/model 标识（`provider_type` + `model`，无 secret/base auth）；AI-first model_said_none 决策保留 confidence + 简短 reason，但不持久化完整输入 context。
- **[EXTERNAL_REVIEW][ABSTRACTION_RULE]**：Task extraction 业务逻辑依赖 `BaseProvider`，不依赖 `OpenAICompatibleProvider` 内部或私有 `_model` 字段（公共 `model` 属性 + `provider_type`）。
- **[EXTERNAL_REVIEW][FALLBACK_RULE]**：structured-output fallback 只由 structured-output 不兼容证据触发（`STRUCTURED_OUTPUT_UNSUPPORTED`，通用 HTTP 错误字段分类），不是每个 generic INVALID_REQUEST；AUTH/RATE/TIMEOUT/NETWORK/MODEL/CONTEXT 不 fallback；总 calls ≤ 2。
- **[EXTERNAL_REVIEW][TIME_CORRECTION]**：只有无年份的过去日期可用跨年推断（"8月5日" 在 8/10 之后 → 明年）；显式给出的过去年份/日期（"2026年8月5日"）必须拒绝为 past，不得静默改写为明年。
- **[EXTERNAL_REVIEW][TEST_SAFETY]**：`CAMPUSCUE_ENV=test` 不得有任何自动路径通向正常应用 DB——test + pipeline enabled + 无显式 `CAMPUSCUE_DB_PATH` → 启动前 fail（config 边界，`database_path_explicit` provenance）。
- **[EXTERNAL_REVIEW][OWNERSHIP_RULE]**：状态判定（confidence vs threshold、deadline 解析）单一属主 = Pipeline（L4/L6），通过 `candidate.pending_confirm` 交给 TaskService 应用；TaskService 不重算 confidence，不持有 threshold；死 `decide_pending_confirm` 已删。
- **[EXTERNAL_REVIEW][DEDUP_KEY_RULE]**：持久化 Task.dedup_key 由单一 canonical helper `build_dedup_key(title, course, deadline)` 定义（normalized title + course 双方已知 + deadline minute），与 Deduplicator 语义一致；不做模糊匹配。
- **[EXTERNAL_REVIEW][INJECTION_DEFENSE]**：QQ 消息与上下文是未信任数据——system prompt 声明其为待分类数据、不服从消息内指令、输入不得覆盖 schema/系统规则；mock 行为测试证明 user 文本永在 user role（防御纵深，不宣称 LLM 注入已解决）。
- **[REPO_CONFIRMED]**：M2b.1.1 落地（302 tests 全绿 + fresh venv 隔离 + Anti-AstrBot）：CONFIG_ERROR/STRUCTURED_OUTPUT_UNSUPPORTED 两个新错误码、ContextCollector resize、config fail-fast 校验、TaskService 所有权清理、dedup key helper、prompt-injection 防御。

## 9L. MEMORY DELTA（M2b.1.2 Fallback Contract Fix）

- **[EXTERNAL_REVIEW][FALLBACK_RULE][CURRENT]**：Structured-output fallback 需要结构化特定证据（error.type/code/message 显式引用 json_schema / response_format / structured_output / "structured output"）。Generic "unsupported"（如 `unsupported_parameter` + "temperature is unsupported"）不足够——必须 INVALID_REQUEST 不 fallback。
- **[EXTERNAL_REVIEW][PROMPT_RULE][CURRENT]**：primary json_schema 路径与 fallback JSON-only 路径必须保留相同的 AI-first 语义与 input-as-data 安全契约。Fallback 只能改变输出强制（response_schema 有无 / "只输出合法 JSON" 规则），不能改变产品含义。实现 = 单一 canonical `build_system_prompt(json_only: bool)`，禁止两份可漂移的大型 prompt。
- **[EXTERNAL_REVIEW][CONTEXT_RULE][CURRENT]**：Fallback 抽取收到与 primary structured 路径相同的有界上下文/信号/当前消息信息（同一 user 消息实例）；禁止 fallback 只用 current_text 重建。
- **[EXTERNAL_REVIEW][DEDUP_CORRECTION][CURRENT]**：双方课程已知且不同时，同标题任务不得仅因双方 deadline 都缺失而 dedup。课程在双方都已知时参与语义身份（无 deadline 分支与有 deadline 分支一致）；`build_dedup_key` 相应只在 course 已知时入键。
- **[REPO_CONFIRMED]**：M2b.1.2 落地（316 tests 全绿 + fresh venv + Anti-AstrBot）：FALLBACK_PROMPT 删除、400 分类收紧、whitespace secret fail-fast、dedup 课程语义修正。

## 9M. MEMORY DELTA（M2b.2 REAL ENV ACCEPTANCE + NapCat Recovery）

- **[USER_STATED][SAFETY_CONSTRAINT][CURRENT]**：用户的主 QQ 账号（大号）**绝不**用作 CampusCue bot；自动化环境工作**禁止**终止/重启/修改大号（包括 taskkill /IM QQ.exe 批量杀进程）。测试 bot 是独立小号。
- **[EXTERNAL_REVIEW][EXECUTION_SAFETY]**：同名桌面进程不能按进程名批量杀（`taskkill /IM QQ.exe` 会同时杀掉用户活动会话与测试 bot）。**必须 PID 归属证明后定向终止**；用户会话 PROTECTED_BY_DEFAULT。
- **[EXTERNAL_REVIEW][ACCOUNT_IDENTITY]**：账号角色（bot vs 用户主号）必须**显式/可证明地映射**后才能迁移配置；不得仅凭 `onebot11_<id>.json` 文件新旧猜测（曾误把用户大号当 bot）。
- **[REAL_ENV_OBSERVATION][NAPCAT]**：NapCat Framework/nativeLoader 前台启动曾产生 `EPIPE: broken pipe`——**stdout/stderr 重定向到文件后初始化成功**（EPIPE 可能是终端管道问题，不证明 Framework 不兼容；未迁移 Shell）。
- **[REAL_ENV_CONFIRMED][NAPCAT]**：当前 M2 REAL 环境 NapCat Framework 可用（重定向启动）；曾出现 `TypeError: Object has been destroyed`（QQ 会话退出时的 unhandledRejection，WS 断开；重连后恢复）。
- **[REAL_ENV_CONFIRMED][M2]**：**真实 QQ 群消息完整链路验证通过**：QQ → NapCat 小号 → OneBot Reverse WS → CampusCue AI-first Pipeline → 真实 DeepSeek Provider → TimeNormalizer/Dedup/TaskService → 真实 SQLite。测试 A-E 全 PASS（hello 共存/明确任务 deadline 精确 2026-08-14 15:59 UTC/普通聊天 skipped 无泄漏/语义重复不创建第二 Task/重启 DB 持久化 + NapCat 自动重连）。
- **[REAL_ENV_CONFIRMED][PROVIDER]**：provider_type=openai_compatible，model=deepseek-chat，structured_mode=**json_fallback**（DeepSeek 拒绝 json_schema，CampusCue 正确回退，≤2 calls，共享 canonical 语义契约）。secret 永不记录。
- **[REAL_ENV_CONFIRMED][AI_FIRST]**：真实普通聊天（hello/问候）到达真实 Provider，has_task=false → skipped Extraction，无 Task，无输入文本泄漏。
- **[REAL_ENV_CONFIRMED][DEDUP]**：重复真实任务消息 → `same_semantic_task` duplicate，Task 数保持 1。
- **[REAL_ENV_CONFIRMED][M1_COMPAT]**：M2 pipeline 启用时 M1 hello Echo 继续工作（send_group_msg retcode 0）。
- **[REAL_MODEL_VARIANCE]**：真实 DeepSeek 对同一任务的 course 提取存在 variance（一次 null 一次 高等数学——取决于消息原文是否含课程名）；确定性代码正确，不加模糊匹配。

## 9N. MEMORY DELTA（M2 Final Continuity Cleanup）

- **[EXTERNAL_REVIEW][M2_TECHNICAL_VERDICT]**：M2 实现与 M2b.2 REAL ENV 链路已通过外部技术审核。M2 FINAL 暂缓仅因连续性文档含 stale 状态（本轮已修复）。
- **[EXTERNAL_REVIEW][CONTINUITY_CORRECTION]**：技术正确的 milestone 也可能在最终连续性门失败——当持久恢复文档含**相互矛盾的 active 状态**时。**AGENT_MEMORY 必须整文件语义扫描，不能只看顶部 CURRENT TRUTH 表**（Section 2 正确但 Section 3 残留旧门 = 复发模式）。
- **[EXTERNAL_REVIEW][DOCUMENTATION_RULE]**：README 当前能力陈述必须跟踪已实现 milestone 状态——M2 实现后不得残留"当前能力仅 M1 / M2+ 未实现"。用 Implemented / Not-yet-implemented 显式区分。
- **[EXTERNAL_REVIEW][DOCUMENTATION_RULE]**：不得手动声明与 pyproject.toml 矛盾的依赖集——**pyproject.toml 是 canonical 依赖源**。
- **[REPO_CONFIRMED]**：M2 Final Continuity Cleanup 落地：AGENT_MEMORY/README/pyproject description 修复；生产源码零修改；测试未重跑（316 为历史证据）。

## 9O. MEMORY DELTA（M3 Reminder）

- **[EXTERNAL_REVIEW][CURRENT]**：M2 FINAL PASS（GitHub baseline 23083cb）。M3 Reminder authorized。M4 remains unauthorized until M3 external final review。
- **[DESIGN_DECISION][M3]**：Reminder DB rows 是 canonical facts；scheduler jobs 是 fully derived/rebuildable runtime state（resync_all 从 facts 重建；确定性 job_id `reminder:<id>`）。
- **[DESIGN_DECISION][M3]**：TaskService 拥有 task create/deadline change/complete/dismiss/delete 的 reminder lifecycle 耦合（ADR-006 强制；可选注入——Reminder 子系统禁用时 M2 行为不变）。
- **[DESIGN_DECISION][M3]**：schema v1→v2 显式迁移（reminders 表）；禁止静默改 schema 而 SCHEMA_VERSION 不变。v0/未知/更新版本拒绝零变更。
- **[DESIGN_DECISION][M3]**：停机期间错过的提醒**不补发**（resync 显式比较 trigger_at <= now → cancel；不依赖 scheduler misfire 默认）。
- **[DESIGN_DECISION][M3]**：Reminder 业务时间用注入 Clock + timezone（无隐藏墙钟）；trigger_at 存 aware UTC。
- **[REAL_ENV_LOCAL][M3]**：本地真实调度器验收 PASS（APScheduler 3.11 真实验证）：任务→3 facts/3 jobs；重启 resync 重建无重复；deadline 变更旧计划取消新计划就位；complete 后全取消 0 jobs 0 投递。
- **[REPO_CONFIRMED][M3]**：344 tests 全绿（+28 M3）；APScheduler 3.11 实测行为：memory jobstore 的 replace_existing 会**追加**而非替换 → 显式 remove-then-add；shutdown 未启动调度器抛 SchedulerNotRunningError → 容错。misfire_grace_time 必须 >0（3.11 拒绝 0）。

## 9P. MEMORY DELTA（M3.1 Reminder Hardening）

- **[EXTERNAL_REVIEW][M3_FINDING]**：**配置存在 ≠ runtime 已接线**。Reminder 配置必须通过真实 composition root 测试（ReminderPolicy 从 RuntimeConfig.reminders 构造：timezone/min_lead/quiet hours 被运行时消费）；移除重复配置真值（tasks.reminders_enabled 删除，唯一真值在 ReminderConfig）。
- **[EXTERNAL_REVIEW][M3_FINDING]**：**quiet-hour 变换必须保留业务不变量：提醒绝不可排在任务 deadline 之后**。前向折叠超过 deadline → clamp 到 quiet_end-1s 同日（仍 < deadline）或丢弃该 intent（23:59 deadline / 凌晨 deadline 测试覆盖）。
- **[EXTERNAL_REVIEW][M3_FINDING]**：**真 resync 用 DB facts 替换派生 scheduler 状态**，不得假定 scheduler 已空——resync_all 先 clear_all 再重建（同进程 stale job 清理测试）。
- **[EXTERNAL_REVIEW][M3_FINDING]**：**schema 迁移必须产生与 fresh bootstrap 相同的域约束**（迁移 SQL 含 reminders CHECK 约束：type/status 闭集），且迁移前必须验证源 schema（表/关键列/schema_meta 恰一行）——malformed/任意 SQLite 带 schema_meta=1 → SchemaRefusedError 零变更。
- **[REPO_CONFIRMED]**：M3.1 落地（354 tests 全绿 + fresh venv + Anti-AstrBot）：ReminderService delivery 默认 NoopDelivery（直接构造 fire 不失败）；DST 测试更新反映 post-deadline 不变量。

## 9Q. MEMORY DELTA（M3.2 Final Gate Fix）

- **[EXTERNAL_REVIEW][M3_FINDING]**：post-deadline guard 单独不足——每个计划提醒必须同时满足：trigger <= deadline **且** trigger 不在 quiet hours 内（07:59:59 仍是 quiet；默认 23-08 窗最后允许时刻是 22:59:59）。
- **[EXTERNAL_REVIEW][M3_FINDING]**：schema_meta 基数（恰一行）是**全局数据库身份不变量**——必须在版本分发（v1/v2/未来）之前验证；不能依赖 SELECT 行序（[1,2] 与 [2,1] 都拒绝）。
- **[EXTERNAL_REVIEW][TESTING_RULE]**：composition-root 契约必须通过真实 composition root 测试（spy 生产 ReminderService 构造器）；测试中手动重建同一对象 ≠ 验证接线。
- **[DESIGN_DECISION][M3.2]**：quiet hours 采用 **overnight-only** 契约（start > end 校验 fail-fast；同日/相等窗口显式拒绝）；canonical `is_inside_quiet_hours` 谓词为折叠/校验/测试单一真源；clamp 目标 = quiet_start 前一刻（22:59:59）。
- **[REPO_CONFIRMED]**：M3.2 落地（363 tests 全绿 + fresh venv + Anti-AstrBot）：_precheck 全局恰一行、composition-root spy 测试、quiet 边界 A-E。

## 9R. MEMORY DELTA（M3.3 Final Recovery Fix）

- **[EXTERNAL_REVIEW][M3_FINDING]**：Reminder 重启恢复有两层：Task facts → reconcile 持久化 Reminder facts → 重建 scheduler 派生 jobs。仅从既有 Reminder 行重建 scheduler jobs 无法治愈：M2→M3 升级任务（reminders 空表）与崩溃间隙（Task commit 成功但 Reminder 规划未完成）。
- **[DESIGN_DECISION][M3]**：startup resync 必须保留匹配的未来 Reminder fact 身份（同 type+trigger_at 保留原 id），只创建缺失 facts、只取消 stale active facts，然后重建 scheduler jobs——重复重启不得造成 fact churn（无取消历史膨胀、无重复 active facts、事实 ID 稳定）。
- **[EXTERNAL_REVIEW][DATA_SAFETY]**：当前 schema 版本标记不足以证明 DB 结构有效——既有 current-version DB 必须在 create_all 前只读结构验证（缺表/缺关键列 → SchemaRefusedError 零变更）；不得用 create_all 当隐式修复。

## 9S. MEMORY DELTA（M3.4 Storage Safety Final Seal）

- **[EXTERNAL_REVIEW][DATA_SAFETY]**：schema 迁移不因异常处理调 rollback 就原子——所有迁移 DDL + 版本号更新必须实际在一个显式事务内执行（BEGIN IMMEDIATE + 逐条 execute + COMMIT/ROLLBACK；不用 executescript，其隐式事务控制可能提交挂起事务）。
- **[EXTERNAL_REVIEW][DATA_SAFETY]**：schema 版本验证必须覆盖该版本的完整 ORM 必需列契约——小部分关键列不能证明既有 DB 与 runtime 兼容（tasks 缺 source_message_id/created_at、reminders 缺 job_id、provider_configs 缺 timeout_s 等都必须拒绝）。
- **[DESIGN_DECISION][M3]**：canonical v1 schema 不含 reminders。schema_meta=1 且已含 M3-only 结构（reminders）的 DB = 半迁移/部分状态 → 拒绝而非猜测/修复（YAGNI）。
- **[REPO_CONFIRMED]**：M3.4 落地（378 tests 全绿 + fresh venv + Anti-AstrBot）：原子迁移（强制中途失败回滚：schema_version 仍 1、无 reminders 表/索引残留）、v1/v2 完整列 manifest、半迁移拒绝字节不变。
- **[REPO_CONFIRMED]**：M3.3 落地（370 tests 全绿 + fresh venv + Anti-AstrBot）：resync_all 真业务对账（Tasks→facts→jobs）、TaskRepository.list_pending_with_deadline 专用查询（不截断）、v1/v2 共享 _validate_application_schema、17_MILESTONES gate 修复。

## 9T. MEMORY DELTA（M4 checkpoint，2026-08-17）

- [EXTERNAL_REVIEW][CURRENT]：M3 FINAL = PASS at baseline 7d22a61b45a3c0110a5ae359e4636b52c3fd2f05；M4 implementation checkpoint is complete locally, but M4 = IMPLEMENTATION_COMPLETE_REAL_ENV_PENDING；M4 FINAL not declared；M5 not authorized。
- [REPO_CONFIRMED]：M4 includes provider-neutral Tool Calling, ToolRegistry, trusted source-scoped Task Tools, CampusAgentRuntime bounded loop, explicit Agent routing, per-thread lock, bounded/LRU conversation threads, conservative CJK ContextBudget, event-timestamp system prompt, configuration/package wiring and peer-review regression tests。
- [REPO_CONFIRMED]：Workspace Agent local evidence = 453 passed; M4 Provider/Agent/Router focused = 44 passed; compileall PASS; Anti-AstrBot PASS; git diff --check PASS。This is not independent External ChatGPT execution。
- [UNCERTAIN][NOT_RUN]：Real Provider Tool Call and Real QQ Agent E2E were not run in this checkpoint。QQ processes and protected primary account were not touched。
- [KNOWN_LIMITATION][M3][OUT_OF_SCOPE]：Task/Reminder cross-repository atomicity remains an open design risk; startup resync_all self-healing is accepted。This checkpoint does not introduce unit-of-work or modify Reminder architecture。

## 9U. MEMORY DELTA（M4.1 static hardening + fresh package isolation，2026-08-18）

- [EXTERNAL_REVIEW][CURRENT]：M3 FINAL = PASS at baseline 7d22a61b45a3c0110a5ae359e4636b52c3fd2f05；M4 = STATIC_HARDENING_COMPLETE_REAL_ENV_PENDING；M4 FINAL NOT declared；M5 NOT authorized。M4.1 静态加固不自动通过 M4 FINAL——Real Provider Tool Call 与 safe independent-test-bot QQ E2E 仍未运行。
- [TEST_CONFIRMED]：M4.1 focused tests（deadline sentinel / explicit clear / Reminder coupling / missing & disabled Source gate / auto_extract=false explicit Agent / ContextBudget single-count / Provider timeout independence / trusted provenance / multi-create limitation / M4 Provider/Agent/Router regressions）passed in a fresh installed-package environment（**88 passed**）。
- [TEST_CONFIRMED]：Full V2 suite passed in a fresh installed-package environment（**466 passed**）。
- [TEST_CONFIRMED]：campuscue.agents / campuscue.tools / jsonschema resolve correctly from fresh V2 package isolation（imports resolved from fresh environment installed V2 package；无 Legacy root / AstrBot / 旧 venv / PYTHONPATH 泄漏）。
- [REPO_CONFIRMED]：M4.1 hardening content——TaskService 公开 `DEADLINE_UNSET` sentinel（省略=不变 / 显式 None=清除 / naive 拒绝）；Agent handler missing/disabled source gate（安全本地回复，不触发 Agent）；AgentContext/ToolContext 新增 runtime-trusted `user_text`（`task_create.source_text_reference` 非模型注入）；ContextBudget 当前输入只计一次；Agent LLM 请求不派生 tool 超时（Provider timeout 独立性）。
- [DESIGN_LIMITATION][M4]：One source message can create at most one Task in the first version because the M2 `(source_id, source_message_id)` uniqueness contract remains unchanged。A second task_create from the same user message is safely returned as failure。No schema v3 was introduced。
- [UNCERTAIN][NOT_RUN]：Real Provider Tool Call and Real QQ Agent E2E were not run in this checkpoint。QQ processes and protected primary account were not touched。
- [REPO_CONFIRMED]：fresh 验证为 Workspace Agent local evidence，非独立 External ChatGPT 执行；compileall PASS / Anti-AstrBot PASS / git diff --check PASS / Secret+PII scan PASS；fresh venv 文件未提交。

## 9V. MEMORY DELTA（M4.2 Real Provider Tool Call，2026-08-18）

- [EXTERNAL_REVIEW][CURRENT]：M3 FINAL = PASS at baseline 7d22a61b45a3c0110a5ae359e4636b52c3fd2f05；M4.1 STATIC HARDENING = PASS at baseline 6e02289d56a0a05bae5db80dd694b05918853959；M4 = REAL_PROVIDER_TOOL_CALL_PASS_QQ_E2E_PENDING；M4 FINAL NOT declared；M5 NOT authorized。Real QQ Agent E2E 是下一门，本 checkpoint 未授权运行。
- [TEST_CONFIRMED][REAL_PROVIDER]：**Real Provider Tool Call = PASS**（2026-08-18）——openai_compatible / deepseek-chat / 真实 httpx transport（api.deepseek.com；secret_reference=CAMPUSCUE_LLM_API_KEY，secret 值不落盘）。真实 Provider 自主发出 `task_list`（模型选择 scope=week/today）+ 自主追加 `task_get` → ToolRegistry → TaskService → 临时真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → 最终回答反映合成 DB 任务；通过 TaskService 改 title 后回答随之变化（数据驱动，非硬编码）；Source A/B 作用域隔离双向验证通过。
- [REPO_CONFIRMED][REAL_GATE_FIX]：真实 OpenAI 兼容端点（DeepSeek）在 tool-call 轮次同时返回辅助 content 文本 + tool_calls；原 `_parse_ok`（M4 §8 双形状设计）硬判 MALFORMED_OUTPUT → 最小聚焦修复：tool_calls 权威、辅助文本丢弃（Agent loop 保持 final-text / tool-call 两种明确形状）；`test_6b_mixed_content_and_tool_calls_keeps_tool_calls` 覆盖新契约；docs/v2/08 同步真实兼容说明。
- [TEST_CONFIRMED]：源码变更后按要求重做 fresh installed-package isolation（`.venv-m42fresh`）；M4 focused **88 passed**；full V2 **466 passed**；compileall PASS；Anti-AstrBot PASS；git diff --check PASS；Secret+PII scan PASS；imports resolved from fresh environment installed V2 package。Workspace Agent local evidence，非独立 External ChatGPT 执行。
- [UNCERTAIN][NOT_RUN]：Real QQ Agent E2E not run in this checkpoint；QQ processes and protected primary account not touched。
- [DESIGN_LIMITATION][M4]：One source message can create at most one Task in the first version（M2 `(source_id, source_message_id)` 唯一约束不变；second task_create safely fails；no schema v3）。

## 9W. MEMORY DELTA（M4.3 Real QQ Agent E2E，2026-08-19）

- [EXTERNAL_REVIEW][CURRENT]：M3 FINAL = PASS at baseline `7d22a61b45a3c0110a5ae359e4636b52c3fd2f05`；M4.1 STATIC HARDENING = PASS at baseline `6e02289d56a0a05bae5db80dd694b05918853959`；M4.2 REAL PROVIDER TOOL CALL = PASS at baseline `3c1b5ab55843a4fb01020e07d785e1eedf4ea9f7`；**M4.3 REAL QQ AGENT E2E = PASS（2026-08-19）**；M4 = IMPLEMENTATION_AND_REAL_ENV_COMPLETE_AWAITING_EXTERNAL_REVIEW；M4 FINAL NOT declared；M5 NOT authorized。
- [REAL_ENV_CONFIRMED][M4.3]：**Real QQ Agent E2E = PASS**——独立 NapCat Shell Windows Node v4.18.19（官方 Release `NapCat.Shell.Windows.Node.zip`，SHA256 已校验）目录 `C:\Tools\NapCat\m43-clean`，`NAPCAT_DISABLE_MULTI_PROCESS=1` 避免 worker `--no-sandbox` bad-option；TEST_BOT 登录（quick login 因手Q 验证回退二维码）→ Reverse WS `ws://127.0.0.1:6199/ws` → CampusCue（`CAMPUSCUE_TASK_PIPELINE=1` + `CAMPUSCUE_AGENT=1` + 真实 SQLite `m4-qq-accept.db` + DeepSeek key 从 Windows Credential Manager 读取，不落盘）。
- [REAL_ENV_CONFIRMED][E2E_CHAIN]：真实 QQ 群消息 `@TEST_BOT 我这周有什么事情？` → @self Agent 激活 → 真实 DeepSeek 自主发出 `task_list` → ToolRegistry → TaskService → 真实 SQLite → tool result 回传 → 第二次真实 Provider 调用 → `send_group_msg` retcode 0 回复任务列表（真实 QQ 收到）。
- [REAL_ENV_CONFIRMED][DATA_DRIVEN]：通过生产 TaskService 将任务标题从“高等数学第三章作业/高等数学”改为“线性代数第四章作业/线性代数”；第二次真实 QQ 查询回复随之显示“线性代数第四章作业”且截止/剩余时间更新——回答随 SQLite 数据变化，非硬编码。
- [REAL_ENV_CONFIRMED][NO_AGENT_ON_NORMAL]：普通不 @ 群消息（日常闲聊）不触发 Agent——无 Agent tool loop、无回复；仅 M2 AI-first TaskPipeline 调用 Provider 判定 `has_task=false` / `status=skipped`（符合 ADR-013 AI-first 设计，不是 Agent Provider 调用）。
- [REPO_CONFIRMED][NAPCAT_ENV]：M4.3 使用官方 NapCat.Shell.Windows.Node v4.18.19；wrapper.node 官方包缺 `crypto.dll`/`ssl.dll`（PE 导入依赖），从本机官方 QQ 安装目录 `C:\Program Files\Tencent\versions\9.9.33-52230\resources\app` 补齐后 native module load PASS；`--no-sandbox` 问题通过 `NAPCAT_DISABLE_MULTI_PROCESS=1` 官方环境变量解决。
- [TEST_CONFIRMED]：M4 focused **88 passed**；full V2 **466 passed**（M4.2 fresh `.venv-m42fresh` 历史证据）；M4.3 真实验收为 Workspace Agent local evidence，非独立 External ChatGPT 执行；CampusCue Git 仓库本轮仅文档更新，无生产源码改动。
- [DESIGN_LIMITATION][M4]：One source message can create at most one Task in the first version（M2 `(source_id, source_message_id)` 唯一约束不变；second task_create safely fails；no schema v3）。

## 9X. MEMORY DELTA（M5 API + Realtime，2026-08-19）

- [EXTERNAL_REVIEW][CURRENT]：M4 FINAL = PASS（External ChatGPT，baseline `3c84ce161ac146986f319bb57c2ae3af6b704c13`）；**M5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；M5 FINAL NOT declared；M6 NOT authorized。
- [USER_STATED][WORKFLOW_PREFERENCE][CURRENT]：优先完成项目；正常安全开发操作由 Workspace Agent 自主执行；避免过度 STOP。
- [DESIGN_DECISION][M5]：final API base path = `/api/v1`；health = `GET /api/v1/health`。
- [DESIGN_DECISION][M5]：API auth = 默认 loopback 无认证；`CAMPUSCUE_REQUIRE_AUTH=1` 或非 loopback 强制 Bearer token；token 只来自 env。
- [DESIGN_DECISION][M5]：SSE = notification only / no replay；bounded per-subscriber queue；慢订阅者断开。
- [DESIGN_DECISION][M5]：Agent API 要求 `source_id`；Runtime 构造 trusted context，禁止 HTTP 注入 provenance。
- [DESIGN_DECISION][M5]：Messages API = extraction projection；不保存完整 QQ 历史。
- [DESIGN_DECISION][M5]：Settings 持久化 = schema v3 `settings` 表；timezone 修改返回 restart_required。
- [DESIGN_DECISION][M5]：Backup = 逻辑 JSON（format_version=1, schema_version=3），restore 单事务替换 + resync；import/export 兼容 `campuscue.tasks` V1。
- [DESIGN_DECISION][M5]：schema v3 = settings 表 + sources.deleted_at（软删除保留 provenance）+ M5 索引；v1→v2→v3 migration atomic。
- [TEST_CONFIRMED]：新增 M5 tests 14（API 10 + realtime 2 + migration 2）；full V2 **480 passed**；fresh installed-package `.venv-m5fresh` non-editable PASS；compileall PASS；Anti-AstrBot PASS；uvicorn local HTTP smoke PASS。Workspace Agent local evidence，非独立 External ChatGPT 执行。

## 9Y. MEMORY DELTA（M5.1 Final Hardening，2026-08-20）

- [EXTERNAL_REVIEW][CHANGES_REQUESTED]：External review of M5 commit `2d34d3382c7c7770536918926b45d1ba1bfc10e4` identified A slow SSE subscriber stream not terminating, B configured heartbeat not consumed, C missing Uvicorn readiness barrier, D duplicate health route, and E realtime lifecycle/completeness evidence gaps。
- [REPO_CONFIRMED][TEST_CONFIRMED]：M5.1 fixed A-D/E with bounded subscriber close state, API heartbeat wiring, owned Uvicorn readiness barrier and rollback, canonical `/api/v1/health`, neutral Adapter `connection.updated`, and post-commit notifier exception isolation。
- [TEST_CONFIRMED]：M5/M5.1 focused **23 passed**；M5.1 new **7 passed**；full V2 **487 passed** in fresh non-editable `.venv-m51fresh`；compileall PASS；Anti-AstrBot PASS；local health/readiness/SSE/occupied-port rollback evidence PASS。These are Workspace Agent local results, not independent External ChatGPT execution。
- [CURRENT]：**M5.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M5 FINAL = NOT YET DECLARED；M6 = NOT_AUTHORIZED**。

## 9Z. MEMORY DELTA（M5.1.1 Final SSE Route Cleanup，2026-08-20）

- [EXTERNAL_REVIEW][CHANGES_REQUESTED]：M5.1 commit `9f0c058146625a78dfbba8745721d73b46707faf` had one remaining early HTTP SSE close edge case: the client could close after `: connected` before `hub.stream()` established its own cleanup。
- [REPO_CONFIRMED][TEST_CONFIRMED]：`/api/v1/stream` outer generator now unsubscribes in `finally`; route-level body-iterator regression confirms early close leaves zero subscribers。
- [TEST_CONFIRMED]：M5/M5.1/M5.1.1 focused **24 passed**；fresh non-editable `.venv-m511fresh` full V2 **488 passed**；compileall PASS；Anti-AstrBot PASS；secret/PII and diff checks PASS。
- [CURRENT]：**M5.1.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；M5 FINAL = NOT YET DECLARED；M6 = NOT_AUTHORIZED**。
- [KNOWN_LIMITATION]：M4 first-version source_message_id uniqueness remains；M5 schema v3 does not change it。M3 Task/Reminder cross-repository atomicity remains open design risk; startup resync_all recovery accepted。

## 9AC. MEMORY DELTA（M6.2 subtle visual polish checkpoint，2026-08-20）

- [REPO_CONFIRMED][CURRENT]：M5 FINAL = PASS；M6.1 保持为已完成 integration baseline；**M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- [DESIGN_DECISION]：M6.2 保留 IA、layout、API、store、router、backend、schema；只改 tokens/shared CSS 和 presentation-level metadata/icon markup。方向是 quiet premium blue-slate + restrained teal，而不是 Product Rewrite。
- [TEST_CONFIRMED]：typecheck/build/Vitest PASS；Playwright full 12 passed（单 worker 保证 shared real harness deterministic）；axe 0；light screenshots `.ai-handoff/visual/m62/`；dark evidence `.ai-handoff/visual/m62-dark/`；m61 baseline screenshots restored from `m6.1-ui-baseline` and not overwritten。
- [REPO_CONFIRMED]：新增 accent/surface/shadow tokens、Home/Tasks/Agent polish、Calendar/Messages/Connections/Providers/Settings shared visual language、Sparkles brand mark、deadline urgency/category/status/confidence detail、dialog/toast/hover/mobile micro-interactions；无 gradient/glass/neon/emoji/robot。
- [CURRENT]：等待 External ChatGPT 对比 M6.1/M6.2 视觉证据；不得声明 M6 FINAL 或进入 M7。

## 9AD. MEMORY DELTA（M6.2.1 final product detail cleanup，2026-08-20）

- [REPO_CONFIRMED][CURRENT]：M6.2.1 完成 M6.2 视觉语言上的产品细节收口；**M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- [DESIGN_DECISION]：保持 M6 IA、M5 contract 和现有页面骨架；Home 读取 Settings timezone 生成动态日期/周条并区分 complete/dismiss；移动底栏为总览/任务/日历/AI/更多，More 使用可访问 bottom sheet；priority canonical 为 `low | normal | high`；共享 helper 统一 category/status/priority 中文 label；theme icon/label 语义修正；移除 topbar 假头像。
- [TEST_CONFIRMED]：typecheck PASS；Vitest 4 passed；focused Playwright 12 passed；axe 0；light evidence `.ai-handoff/visual/m621/`；dark evidence `.ai-handoff/visual/m621-dark/`；m61/m62/m62-dark 未覆盖。
- [CURRENT]：等待 External ChatGPT 对比 M6.1/M6.2 基线与 M6.2.1 新证据；不得声明 M6 FINAL 或进入 M7。

## 9AE. MEMORY DELTA（M6.3 visual character pass，2026-08-20）

- [REPO_CONFIRMED][CURRENT]：创建并推送 `m6.2.1-ui-baseline`，完成 M6.3 Visual Character Pass；**M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- [DESIGN_DECISION]：以 Cue Line + Cue Dot 为轻品牌母题；通过 section tint、page identity、structured empty states、自然内容比例、Tasks/Agent/Calendar/Home 重点节奏和其余页面统一细节增强辨识度；不改 API、业务、router、store、backend、schema，不新增图片或渐变/玻璃/neon。
- [TEST_CONFIRMED]：typecheck/build PASS；Vitest 4 passed；focused Playwright 12 passed；axe 0；real integration 两条测试分别 PASS；light `.ai-handoff/visual/m63/`、dark `.ai-handoff/visual/m63-dark/`；m61/m62/m621 evidence preserved。
- [CURRENT]：等待 External ChatGPT 对比 M6.2.1 baseline 与 M6.3 视觉证据；不得声明 M6 FINAL 或进入 M7。

## 9AB. MEMORY DELTA（M6.1 WebUI integration hardening checkpoint，2026-08-20）

- [EXTERNAL_REVIEW][CHANGES_REQUESTED]：M6 initial implementation had frontend/backend contract gaps: `completed` vs canonical `done`, named SSE events not consumed, fake Settings `language`, hardcoded Calendar, mock-only integration, and incomplete CRUD/system flows。
- [REPO_CONFIRMED][CURRENT]：M5 FINAL = PASS；M6 = CHANGES_REQUESTED（已按审核修复）；**M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- [TEST_CONFIRMED]：真实 isolated M5 FastAPI + SQLite + RealtimeHub + deterministic local fake provider harness passed task mutation → authenticated named SSE → REST refresh；full Playwright 12 passed；typecheck/build/Vitest/axe passed；page evidence at `.ai-handoff/visual/m61/`。
- [REPO_CONFIRMED][DESIGN_DECISION]：M6.1 frontend uses canonical REST for state; fetch-based authenticated SSE consumes named events and triggers REST refresh; no token URL query; system/settings APIs use backend allowlist; real deadline/calendar and CRUD/test/delete/toggle flows are used。
- [CURRENT]：等待 External ChatGPT review；不得声明 M6 FINAL 或进入 M7。

## 9AA. MEMORY DELTA（M6 WebUI implementation checkpoint，2026-08-20）

- [HISTORICAL]：M5 FINAL = PASS before M6 authorization；initial M6 implementation checkpoint was superseded by M6.1 integration hardening。
- [REPO_CONFIRMED][DESIGN_DECISION]：`v2/web/` uses Vue 3 + TypeScript + Vite + Vue Router + Pinia + Lucide. Routes cover Home, Tasks, Messages, Calendar, Agent, Connections, Providers, Settings.
- [TEST_CONFIRMED]：M6 typecheck/build PASS；Vitest 2 passed；Playwright 9 passed；axe violations 0；responsive screenshots generated at 390/599/768/1024/1440. Synthetic fixtures contain no real QQ IDs, message content, tokens, or provider secrets.
- [DESIGN_DECISION]：M5 REST is canonical; SSE is notification-only with reconnect/backoff + REST refresh. Agent UI renders non-empty `tool_activity` only; backend currently returns empty activity and the UI does not fake it.
- [CURRENT]：External visual review is the next gate. Do not declare M6 FINAL or enter M7。

## 9AH. MEMORY DELTA（M6.4 information layering pass，2026-08-20）

- **[REPO_CONFIRMED][CURRENT]**：`m6.3-ui-baseline` 指向 `5152bc6b5008e8c6fdf2cf28ff8040d87e416699`；M6.4 已完成；**M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized。
- **[DESIGN_DECISION]**：M6.4 采用 three-level information hierarchy：primary immediately visible，context nearby/collapsible，advanced only after action。Tasks filter/More/context aside、Agent context rail/mobile sheet/four prompts、Messages master-detail、Calendar selected-day agenda、Connections/Providers/Settings advanced disclosure are presentation-layer changes；API/store/router/backend/schema/business logic frozen。
- **[TEST_CONFIRMED]**：fresh installed-package `.venv-m64fresh` full V2 488 passed；WebUI typecheck/build/Vitest 4/focused Playwright 16/axe 0/real integration 2 passed；m64 light/dark screenshots generated；compileall/Anti-AstrBot/diff-check/secret-PII PASS。
- **[CURRENT]**：等待 External ChatGPT 对比 M6.3 baseline 与 M6.4 evidence；不得声明 M6 FINAL 或进入 M7。

## 9AI. MEMORY DELTA（M6.5 visual depth & product composition pass，2026-08-20）

- **[REPO_CONFIRMED]**：创建并推送 `m6.4-ui-baseline` → `26392e633b1ab47bfe39c1831c774c638f9b7076`；m63/m64 evidence 保持未覆盖。
- **[DESIGN_DECISION]**：CampusCue 采用 editorial productivity / quiet premium / academic workspace 的页面构图；surface hierarchy、typography scale、section contrast 和 whitespace 是主层；玻璃拟态只在 Agent context/composer、Home focus、状态/检查器/对话框等局部使用。
- **[SAFETY]**：`backdrop-filter` 有实色 fallback；长列表、正文、设置表单不使用持续模糊；透明度、边缘高光、阴影按明暗主题适配，文字对比度优先。
- **[VERIFIED]**：typecheck/build PASS；Vitest 4；focused Playwright 16；axe 0；real integration 2；m65 light/dark evidence PASS；responsive 390/768/1024/1440 PASS。
- **[CURRENT]**：**M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；M6 FINAL NOT declared；M7 NOT authorized；等待外部视觉对比。

## 9AJ. MEMORY DELTA（M6.5.1 real Glassmorphism correction，2026-08-20）

- **[REPO_CONFIRMED]**：Starting HEAD `524e4a13a2ba257fa5b04194219c17c9d6cd068c`；本轮不 amend 旧 M6.5 commit。
- **[DESIGN_DECISION]**：按 VibeHub 严格 anatomy 建立真实 Glass：可感知 Atmospheric Backdrop、分级半透明 Tint、按层级调节 Blur、top/left Edge Light、只在悬浮关系使用的 Soft Shadow；文字对比优先，提供 solid/tinted fallback。
- **[SCOPE]**：第一阶段仅 App Shell/Home/Tasks/Agent；Dark 和 Neumorphism 冻结；不改 M6.4 信息结构、dataset、IA、API、store、router、backend、schema 或业务逻辑。后续 Calendar/Messages/Connections/Providers/Settings/Dialog/Sheet 统一必须等 Glass 外部审核。
- **[VERIFIED]**：专用 Glass material test 1 passed；M6 focused Playwright 16 passed；typecheck/build PASS；axe 0；marker screenshot 证明颜色区域能透过 Agent glass 被 tint + blur 感知；evidence 在 `.ai-handoff/visual/m651/glass/`。
- **[CURRENT][HISTORICAL]**：**M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS**；GLASS FINAL NOT declared；DARK REVIEW/NEUMORPHISM REVIEW pending；M6 FINAL NOT declared；M7 NOT authorized。

## 9AK. MEMORY DELTA（M6.5.2 Glass refinement & productization，2026-08-20）

- **[EXTERNAL_VISUAL_REVIEW][M6.5.1]**：Glass direction = PASS；Atmospheric Backdrop、Tint、Blur、Edge Light、Shadow、Contrast 材质成立。剩余问题是 backdrop 稍强、tier 未统一、utility controls 偏 SaaS opaque、Home nested white、Tasks dead canvas/raw ISO、mobile separation。
- **[DESIGN_DECISION]**：M6.5.2 固化 Base / Primary / Context / Raised / Floating semantic material tiers；backdrop 支持层级但不成为主视觉；高频 rows/正文保持实色可读；raw ISO timestamp 永不直接显示给用户。
- **[REPO_CONFIRMED]**：Stage 1 仅 App Shell/Home/Tasks/Agent；新增 `.ai-handoff/visual/m652/glass/` 五张 evidence；`.ai-handoff/visual/m651/glass/` 从 `m6.5.1-glass-baseline` 恢复，旧 evidence 未覆盖；Settings backup preview 也改用共享本地化日期 formatter。
- **[TEST_CONFIRMED]**：M6.5.2 focused 2 passed；M6 focused 16；M6.5.1 regression 1；real integration 2；WebUI typecheck/build/Vitest 4；fresh installed-package full V2 488；compileall/Anti-AstrBot/diff-check/Secret+PII/axe/overflow/console/theme/fallback PASS。
- **[CURRENT]**：**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；GLASS FINAL NOT declared；DARK REVIEW = PENDING；NEUMORPHISM REVIEW = PENDING；M6 FINAL NOT declared；M7 NOT authorized。STOP for external visual review。

## 9AL. MEMORY DELTA（M6.5.3 Dark UI Stage 1，2026-08-21）

- **[REPO_CONFIRMED]**：`m6.5.2-glass-baseline` 已推送并指向 `63d7aeb4177b61bc73bffa336d6743e50c780559`；M6.5.2 Glass evidence 未覆盖。
- **[DESIGN_DECISION]**：Dark 独立于 Glass，采用低眩光 solid-surface productivity workspace；层级由 luminance/tint/spacing/elevation 表达，只有 focus/selected/primary/小 AI signal 使用克制 accent；Stage 1 只做 App Shell、Home、Tasks、Agent、Settings selector，Stage 2 暂缓。
- **[REPO_CONFIRMED]**：新增 dark token system 与 Dark scoped CSS；Home/Tasks/Agent/Settings Dark surfaces 完成；selector 显示 Glass/Dark 但内部仍兼容 light/dark；无 backend/API/store/router/schema/business logic 变化。
- **[TEST_CONFIRMED]**：Dark focused 2、M6 focused 16、M6.5.2 Glass focused 2、real integration 2；typecheck/build/Vitest/Axe/overflow/console/theme persistence/Glass fallback/mobile composer safety PASS；Dark evidence `.ai-handoff/visual/m653/dark/`。
- **[CURRENT]**：**M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；**M6.5.3 DARK STAGE 1 = PASS**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**；DARK FINAL、GLASS FINAL、M6 FINAL NOT declared；NEUMORPHISM/M7 NOT_AUTHORIZED。STOP for external visual review。

## 9AM. MEMORY DELTA（M6.5.3 Dark UI Stage 2，2026-08-21）

- **[REPO_CONFIRMED]**：Stage 2 基于 `5572811843d3bf5fb3bab5fc6d81f1955ffac7ce`，并创建 `m6.5.3-dark-stage1-baseline` rollback tag；Glass 与 Stage 1 evidence 不覆盖。
- **[DESIGN_DECISION]**：Dark Stage 2 完成 Calendar/Messages/Connections/Providers/Settings、Dialog/Sheet/Toast/Empty/Loading/Offline/Reconnecting；Dark 继续独立于 Glass，不进入 Neumorphism。
- **[REPO_CONFIRMED]**：Theme Selector 不再依赖 nth-child CSS 伪文案；实际 labels 为 `跟随系统 / 玻璃拟态 / 深色界面`；`system` media sync 与 persistence 已覆盖。
- **[EVIDENCE]**：`.ai-handoff/visual/m653-stage2/dark/` 和 `.ai-handoff/visual/m653-stage2/compare/`。
- **[CURRENT]**：Stage 1 PASS；M6.5.3 Dark implementation complete awaiting external visual review；Dark Final、Glass Final、M6 Final 未声明；Neumorphism/M7 未授权。STOP。
- **[REPO_CONFIRMED][M6.5.4]**：Neumorphism implementation complete awaiting external visual review。三材质切换与本地持久化已覆盖；Neu 生产样式无 Glass 核心依赖，使用不透明同材质 canvas、统一光源、克制 raised/inset 阴影，并保持内容密度与对比度优先。
- **[ARCHITECTURE_DECISION][THEMES]**：前端视觉风格与 canonical backend appearance contract 分离：`data-theme` 继续表达 `system/light/dark`，`data-visual-theme` 表达 `glass/dark/neumorphism`；不为 Neumorphism 发明后端 theme enum，不改 API/schema。
- **[CURRENT_GATE][M6.5.4]**：`M6.5.4 NEUMORPHISM = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW`；`NEUMORPHISM FINAL`、`GLASS FINAL`、`DARK FINAL`、`M6 FINAL` 均 `NOT YET DECLARED`；`M7 = NOT_AUTHORIZED`。
- **[EXTERNAL_REVIEW][M6.5.4.1]**：Neumorphism material implementation = PASS；Final blocker was conflicting user-facing Appearance Mode and Visual Style controls，已收敛为单一 System / Glass / Dark / Neumorphism selector。
- **[PRODUCT_DECISION][THEME_UX]**：System resolves to Glass on light OS appearance and Dark on dark OS appearance；explicit Glass/Dark/Neu are OS-independent；reload persistence and live System OS switching are required.
- **[ARCHITECTURE_DECISION][THEME_UX]**：Canonical backend enum remains `system/light/dark`; frontend-only material preference persists locally and never sends `theme=neumorphism`。
- **[CURRENT_GATE][M6 FINAL CLOSURE CANDIDATE]**：旧 Appearance selector/template/CSS 已删除；三主题最终回归与 `.ai-handoff/visual/m6-final-candidate/` 证据已生成；`M6.5.4.1 THEME UX = PASS`；`GLASS FINAL`、`DARK FINAL`、`NEUMORPHISM FINAL` 均 `AWAITING_EXTERNAL_FINAL_REVIEW`；`M6 FINAL = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_FINAL_REVIEW`；`M7 = NOT_AUTHORIZED`。
