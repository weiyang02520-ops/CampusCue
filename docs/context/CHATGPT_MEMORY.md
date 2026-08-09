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

## 1. CURRENT TRUTH（截至 2026-08-09 M0.1）

| 项 | 值 | Provenance |
|---|---|---|
| 项目 | CampusCue V2（课讯）——校园事务 AI Agent 平台 | [USER_STATED] |
| 当前 Milestone | M0.1 REVIEW FIX 完成；**M0 = PASS（条件），M1 = READY_NOT_STARTED** | [EXTERNAL_REVIEW] |
| M0.1 结论 | 架构方向 PASS；文档精度 CHANGES_REQUESTED → 已全部修复 | [EXTERNAL_REVIEW] |
| V2 立项原因 | V1 = AstrBot Runtime + CampusCue 业务层（main.py:44-47 InitialLoader；astrbot/ 完整目录；底座 4 处侵入）；V2 零 AstrBot 依赖 | [REPO_CONFIRMED] |
| V1 仓库 | weiyang02520-ops/CampusCue @ `db35d77`（单 commit 发布，public） | [REPO_CONFIRMED] |
| AstrBot 基准 | commit `30e20318c`（本地副本已 checkout） | [EXTERNAL_REVIEW 固定] |
| V2 仓库 | 同 V1 仓库（docs/v2/ 与 .ai-handoff/ 已推入）；**current remote HEAD：RESOLVE FROM GIT/GITHUB AT RECOVERY TIME（不维护为长期 Memory 字段）** | [REPO_CONFIRMED] + [EXTERNAL_REVIEW] |
| 双 Memory | docs/context/CHATGPT_MEMORY.md + AGENT_MEMORY.md（本轮建立） | [DESIGN_DECISION] |

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

## 14. CURRENT CAMPUSCUE STATE（M0.1 结束时）

- M0 = PASS（外部审核条件性通过，finding 已修复）
- M1 = READY_NOT_STARTED（严禁开始）
- 仓库 HEAD：**RESOLVE FROM GIT/GITHUB AT RECOVERY TIME**（动态 HEAD 不维护为长期 Memory 字段；M0.2 起规则）。历史 checkpoint：M0 commit `6480ad2`；M0.1 commit `3d70da1`
- 未验证项：无代码、无 REAL ENV、无视觉（M6 才有）
- 已知缺口（V1 遗留）：B12 时区硬编码（M2 修）、B13 LLM 测试缺口（M2 修）

## 15. OPEN QUESTIONS

- 无阻塞性问题。M1 启动前等待外部 ChatGPT 确认 M0 PASS + 发布 M1 prompt。

## 16. HISTORY / TIMELINE

| 日期 | 事件 | commit |
|---|---|---|
| 2026-08-03 | V1 七轮修复完成（399 tests） | —（交付包） |
| 2026-08-09 | V1 发布 public 仓库 | `db35d77` |
| 2026-08-09 | V2 M0：研究+审计+设计文档 | `6480ad2` |
| 2026-08-09 | V2 M0.1：外部审核修复 + 双 Memory | `3d70da1` |
| 2026-08-09 | V2 M0.2：最终一致性修复（4 项）+ Memory 语义规则 | 本轮 |
| 2026-08-09 | V2 M0.1：外部审核修复 + 双 Memory | 本轮 |
