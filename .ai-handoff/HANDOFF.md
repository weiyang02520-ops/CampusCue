# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2 Final Continuity Cleanup v2）

- **本轮**：外部 ChatGPT 复核 v1 清理后发现**恰两个**残留 stale 矛盾（README 底部"仅 websockets"依赖行 + 17_MILESTONES M2b.2"未开始"），本 v2 轮仅修这两个
- **状态**：M2 技术实现 + REAL ENV 验收完成；**M2 = AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW；M2 FINAL = NOT YET DECLARED；M3 = NOT_AUTHORIZED**

## 本轮完成（v2 清理）

1. **[A] README 行 128 stale 依赖行**：`运行时依赖仅 websockets（M1 实测 16.0/Python 3.14）` → `运行时依赖以 pyproject.toml 为准`（历史 websockets 证据标注为"当时单一依赖证据，不代表当前完整依赖集"）
2. **[B] 17_MILESTONES 行 33 M2 状态**：`M2b.2（未开始）/ M2 最终未 PASS` → `M2b.2（完成，REAL_ENV PASS 2026-08-10）/ M2 TECHNICALLY_COMPLETE AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW / M2 FINAL NOT YET DECLARED / M3 NOT_AUTHORIZED`
3. **[额外] AGENT_MEMORY §17 STOP RULE 示例**：`如 M1=PASS, M2=READY_NOT_STARTED` 旧示例 → 改为当前门示例（消除歧义）

## 本轮完成（连续性清理）

1. **[A] AGENT_MEMORY stale 修复**：Section 2/3/18 语义扫描——旧" M2b.1 AWAITING / M2b.2 NOT_AUTHORIZED / 下一步 M2b.2"已修正为"M2b.1 PASS / M2b.2 REAL_ENV PASS / M2 TECHNICALLY_COMPLETE AWAITING_EXTERNAL_FINAL_CONTINUITY_REVIEW / M3 NOT_AUTHORIZED"；代码状态表改为中性描述（M1+M2 已实现，316 为 checkpoint 证据非代码身份）
2. **[B] README 顶层矛盾修复**：删"当前能力仅 M1 / M2+ 未实现"；改为 Implemented（M1 QQ runtime + M2 AI-first task extraction）vs Not yet implemented（Reminder/Agent/API/WebUI）明确区分
3. **[B] README 架构双路径**：Path A EchoHandler（M1）+ Path B TaskPipeline → Provider → TimeNormalizer → TaskService → SQLite（M2）
4. **[B] README 依赖准确**：改为"以 pyproject.toml 为准（canonical source）"，不再手动断言仅 websockets
5. **[C] pyproject 描述**：`(M1: QQ runtime)` → milestone-neutral `independent campus affairs AI agent platform`（version/deps/packages/build 未动）
6. **[11] NapCat 措辞**：改为"2026-08-10 本机实测前台触发 EPIPE、重定向成功——本地观察非普适规则"

## 测试

- **未重跑**（本轮零生产源码修改；316 passed 为 M2b.2 历史 Workspace Agent 证据保留）
- 轻量校验：git diff、markdown/state 语义扫描、secret scan、PII scan

## AGENT_DISCOVERED_DELTA（M2 Final Continuity）

- [DESIGN_CHANGE]：AGENT_MEMORY 更新为 M2 TECHNICALLY_COMPLETE 状态；README 重构为 Implemented/Not-yet 双区
- [RECOMMENDED_MEMORY_PROMOTION]：见 CHATGPT_MEMORY §9N（CONTINUITY_CORRECTION / DOCUMENTATION_RULE ×2）

## REAL ENV

- M2b.2 REAL ENV VERIFIED 保留（2026-08-10）；本轮无真实环境操作

## 下一步

- 外部 ChatGPT 最终连续性复核 → M2 FINAL PASS → M3（Reminder）授权

## 本轮修改文件

- 修改：docs/context/AGENT_MEMORY.md（stale 语义扫描）、v2/README.md（能力现状/架构/依赖/NapCat 措辞）、v2/pyproject.toml（仅 description）、docs/context/CHATGPT_MEMORY.md（§9N）、.ai-handoff/（HANDOFF/PROJECT_STATE/REVIEW_REQUEST/STATUS/CHANGELOG）
- **v2/src/、tests/ 零修改**
