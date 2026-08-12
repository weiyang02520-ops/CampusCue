# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M3.3 Final Recovery Fix）

- **本轮**：外部 ChatGPT 对 M3.2 复核 = PASS；M3 FINAL = CHANGES_REQUESTED——1 个主要 reminder 对账缺口（A）+ 2 个一致性/安全小问题（B/C）
- **状态**：M3 = FINAL_RECOVERY_FIX_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M3 FINAL = NOT YET DECLARED；M4 = NOT_AUTHORIZED**

## 本轮完成（M3.3）

1. **[A] resync_all 真业务对账**：`Tasks → reconcile Reminder facts → rebuild scheduler jobs`（不再只从既有 facts 重建 jobs）：
   - clear 派生 jobs → 枚举**所有**相关任务（`TaskRepository.list_pending_with_deadline` 专用查询，不截断）→ 每个任务用同一 Clock/timezone/policy/quiet 规则计算 DesiredReminder → 对账：
     - 匹配的有效未来 facts（同 type+trigger_at）**保留身份**（重启不重建）
     - 缺失 desired facts **创建**
     - 不再 desired 的 stale scheduled facts **取消**
   - done/dismissed/pending_confirm/no-deadline 任务 → 无 active facts（stale 取消）
   - past/missed 不重建不补发
   - 之后只 schedule 有效 canonical facts
   - **幂等**：unchanged task → resync → 同 fact IDs + 同 job ids + 无 cancelled-history 增长
2. **[B] 当前 v2 结构验证**：`_validate_application_schema`（v1/v2 共享）+ `_precheck` 在 create_all 前对既有 v2 DB 只读验证（缺 reminders 表/缺 tasks 关键列 → SchemaRefusedError 零变更）；fresh DB 正常 bootstrap、valid v1 走 owned migration、valid v2 幂等重开
3. **[C] 17_MILESTONES gate 修复**：M2 FINAL PASS @ 23083cb + M3 FINAL_RECOVERY_FIX_COMPLETE AWAITING_EXTERNAL_REVIEW + M3 FINAL NOT YET DECLARED + M4 NOT_AUTHORIZED

## 测试

- **370 passed**（+7 M3.3：迁移回填 1/崩溃修复 1/部分对账 1/非 active 无提醒 1/v2 结构 3）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`，370）
- M3 系列 54 个测试全绿

## AGENT_DISCOVERED_DELTA（M3.3）

- [DESIGN_CHANGE]：resync_all 从"facts→jobs 重建"升级为"Tasks→facts 对账→jobs 重建"（M2→M3 升级/崩溃间隙治愈）
- [REPO_CONFIRMED]：v1/v2 共享 `_validate_application_schema`（表+关键列+版本前缀）；TaskRepository.list_pending_with_deadline 不分页截断
- Memory Delta 见 CHATGPT_MEMORY §9R（3 条 M3_FINDING/DESIGN_DECISION/DATA_SAFETY）

## REAL ENV

- M3 系列均为 LOCAL REAL SCHEDULER（无 QQ）；M2b.2 REAL ENV 保留；用户 QQ/NapCat 未触碰

## 下一步

- 外部 ChatGPT M3 最终复核（含 M3.1+M3.2+M3.3）→ M3 FINAL PASS → M4 授权

## 本轮修改文件

- 修改：services/reminder_service.py（resync 对账）、repositories/repositories.py（list_pending_with_deadline + list_scheduled_for_task）、storage/database.py（_validate_application_schema + v2 前置验证）、docs/v2/17_MILESTONES.md
- 新增：tests/integration/test_m33_recovery.py（7 tests）
- 修改：Memory（双）、.ai-handoff/
