# HANDOFF.md

> M0.1 REVIEW FIX 交接记录。由工作区 AI 在 checkpoint 前更新。

## 本轮目标

执行 M0.1：修复外部审核 14 项文档 finding、建立双 Memory、更新 handoff、checkpoint 后 STOP。**未创建任何 V2 正式代码。**

## 本轮完成

### 外部审核 finding 修复（B~N 全部应用）

| Finding | 修改 |
|---|---|
| B llm.py 耦合矛盾 | 02 表：MEDIUM（走 AstrBot provider）→ **NONE/LOW**（plain HTTP 无依赖）+ REWRITE_INTEGRATION；16 同步 |
| C stop() 过度绝对化 | 03/19：**显式有序 lifecycle-owned cleanup**（非严格逆序）；Platform 写 abstract requirements run()/meta() + 基类其余方法 |
| D Reverse WS 所有权 | 04 重写：**NapCat=CLIENT / CampusCue=SERVER**；断线恢复模型（NapCat 重连 + stale replacement）；server 配置项（host/port/path/token）；07/17 同步 |
| E 帧关联 | 04 新增：Event Frame vs Action Response Frame 分类；echo correlation（unique echo → pending Future → 匹配回帧；timeout/pending cleanup/断连 fail-all）；**禁把 action response 当 CampusEvent** |
| F 队列背压 | 04/07：**有界队列**（maxsize 配置）+ `await put` 背压 + shutdown drain |
| G transport dedup | 04/05：`(self_id, message_id)` bounded TTL dedup，与 M2 semantic dedup 区分 |
| H Guard 范围 | 04/17：M1 Guard 不做 source-enabled；只做 valid/self/duplicate/rate；SourcePolicy 自 M2 |
| I Provider 前移 | 08/17/10：**M2a Provider Foundation**（BaseProvider/LLMRequest/LLMResponse/Error taxonomy/OpenAICompatible/最小 Manager/structured output/secret_reference，无 Agent 无 Tool）；M4 只加 Tool/Agent |
| J M2 仓储 | 06/09/17：M2 实现 SourceRepository + ExtractionRepository + SourceService（不等 M5） |
| K 删消息页验收 | 17：M2 验收改 DB 断言（source/extraction/task row + deadline + dedup），非 Web 页面 |
| L 阶段激活 | 10：L0-L7 自 M2；L8 自 M3；L9 自 M5；TaskService 钩子可选/惰性不依赖假实现 |
| M Runtime 激活表 | 07：Milestone 激活表（M1 只 Config/EventBus/Router/Adapter/Echo） |
| N Outbound 直连 | 05/04：Handler → dispatcher → Adapter.send()，**不经 EventBus** |

### 双 Memory 建立（O~Z）

- `docs/context/CHATGPT_MEMORY.md`：外部 ChatGPT 长期认知（17 节：RECOVERY MODE / CURRENT TRUTH / GLOBAL WORKING MODE / USER INTENT / DECISION MODEL / PRODUCT INTENT+TASTE / ARCHITECTURE INTENT / HISTORY / REJECTED-SUPERSEDED / REVIEW FINDINGS / MEMORY PROTOCOL / provenance 标签 / 时间线）
- `docs/context/AGENT_MEMORY.md`：Workspace Agent 执行认知（18 节：BOOTSTRAP / TRUTH / GATE / RULES / 依赖方向 / AstrBot 边界 / FAILURE MODES / EVIDENCE / MODIFY PROTOCOL / YAGNI / VERIFY LEVELS / NO-VISION / NO-EMOJI / SECRET / CHECKPOINT / MEMORY 维护 / STOP / NEXT TASK）
- 两文件均含 `[USER_STATED]` 全局工作流（双模型接力）与 Memory 协议

## 实际修改文件

- docs/v2/02、03、04（重写）、05、06、07、08、09、10_TASK_PIPELINE、16、17、19
- docs/context/CHATGPT_MEMORY.md、AGENT_MEMORY.md（新增）
- .ai-handoff/：PROJECT_STATE / STATUS / HANDOFF / REVIEW_REQUEST / CHANGELOG_AI / NEXT_TASKS（本轮全部更新）

## 真实测试

- 无代码变更，无测试运行（M0.1 纯文档）
- 执行验证：Markdown 一致性检查（AD 检查项）、reference path 验证、Anti-AstrBot 表述一致性、Milestone dependency 一致性、secret scan、git diff inspection
- **确认：未创建任何正式 V2 source code**

## Mock Tests / 未验证

- 未运行任何测试（无被测代码）
- 未做真实 QQ / NapCat 联调（M1 验收）

## AGENT_DISCOVERED_DELTA（W 协议）

None beyond externally requested corrections.

（本轮全部变更均来自外部审核 finding；无新增仓库事实/设计冲突/运行时发现。）

## Known Bugs

- V1 审计新发现 B12（时区硬编码）、B13（LLM 测试缺口）已入 13_BUG_LESSONS.md，M2 修

## Architecture Changes / Decisions

- M0.1 修正 14 项（见上表）；双 Memory 协议（docs/context/）；REJECTED/SUPERSEDED 见 CHATGPT_MEMORY §9

## Branch / Remote / Base

- 仓库：weiyang02520-ops/CampusCue（public）
- 本次提交：docs: apply M0 external review and bootstrap AI memory
- Base：6480ad2（M0 commit）

## External Review Focus

- 见 REVIEW_REQUEST.md（14 项 finding 修复对照 + 双 Memory 验收）
