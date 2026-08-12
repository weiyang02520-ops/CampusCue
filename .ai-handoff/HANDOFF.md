# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M3.2 Final Gate Fix）

- **本轮**：外部 ChatGPT 对 M3.1 复核 = PASS，M3 FINAL = CHANGES_REQUESTED——仅 3 项窄修复（A quiet 窗外部不变量 / B schema_meta 全局单行 / C composition-root 接线测试）
- **状态**：M3 = FINAL_FIX_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M3 FINAL = NOT YET DECLARED；M4 = NOT_AUTHORIZED**

## 本轮完成（M3.2）

1. **[A] quiet-hours 外部不变量**：canonical `is_inside_quiet_hours(local_dt, policy)` 谓词（折叠/校验/测试单一真源，不复制）；clamp 目标改为 **quiet_start 前一刻**（默认 23-08 → 22:59:59，不再是错误的 07:59:59 仍在 quiet 内）；最终过滤加"不在 quiet 内"硬不变量（trigger<=deadline AND 不在 quiet AND >=now+min_lead）；**overnight-only 契约**：ReminderPolicy.__post_init__ 校验 start>end（同日/相等/越界 fail-fast），quiet_end=0 合法
2. **[B] schema_meta 全局恰一行**：`_precheck` 在版本分发（v1/v2/未来）**之前**要求 len(rows)==1——[1,2] 与 [2,1] 都 SchemaRefusedError 零变更（不依赖 SELECT 行序）；_validate_v1_schema 保留防御性检查
3. **[C] composition-root 接线测试**：spy 生产 `ReminderService.__init__`（不复制 wiring 逻辑）→ 走真实 `CampusRuntime._init_task_pipeline` → 断言构造的 timezone=America/New_York + ReminderPolicy(min_lead=120, quiet 22-09)

## 测试

- **363 passed**（+9 M3.2：quiet 边界 A-E 5 / schema_meta [1,2]+[2,1] 2 / composition-root 1 / 其余）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`，363）
- M3 系列 47 个测试全绿

## AGENT_DISCOVERED_DELTA（M3.2）

- [DESIGN_CHANGE]：quiet 窗改为 overnight-only 契约（YAGNI：产品只要求 23-8）；非 overnight 配置显式拒绝而非静默误释
- [REPO_CONFIRMED]：schema_meta.schema_version UNIQUE 约束使"多行"测试必须用不同 version 值；[1,2]/[2,1] 两种顺序均被 _precheck 拒绝
- Memory Delta 见 CHATGPT_MEMORY §9Q（3 条 M3_FINDING + TESTING_RULE + DESIGN_DECISION）

## REAL ENV

- M3/M3.1/M3.2 均为 LOCAL REAL SCHEDULER（无 QQ）；M2b.2 REAL ENV 保留；用户 QQ/NapCat 未触碰

## 下一步

- 外部 ChatGPT M3 最终复核（含 M3.1+M3.2）→ M3 FINAL PASS → M4 授权

## 本轮修改文件

- 修改：tasks/reminder_policy.py（is_inside_quiet_hours + overnight-only 契约 + clamp 修正）、storage/database.py（_precheck 全局恰一行）
- 新增：tests/integration/test_m32_final_gate.py（9 tests）
- 修改：Memory（双）、.ai-handoff/（HANDOFF/PROJECT_STATE/STATUS/REVIEW_REQUEST/CHANGELOG）
