# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M3 Reminder）

- **本轮**：M3 Reminder 里程碑——DB reminder facts + ReminderService + APScheduler 3.11 集成 + TaskService 生命周期联动 + schema v1→v2 迁移 + 本地真实调度器验收
- **状态**：M3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M3 FINAL = NOT YET DECLARED；M4+ = NOT_AUTHORIZED**
- **Gate**：M0-M2 全部 FINAL PASS（含 M2b.2 REAL ENV @ 23083cb 授权）

## 本轮完成（M3）

1. **schema v1→v2 迁移**：`SCHEMA_VERSION=2`；`_precheck` 读版本（零变更）→ v1 DB owned migration（建 reminders 表 + version bump，保留全部旧数据）→ v2 幂等重开；v0/更新/未知 → SchemaRefusedError 零变更
2. **Reminder 域**：`ReminderType`（day_before/hours_before/deadline）+ `ReminderStatus`（scheduled/fired/cancelled）闭集枚举；Reminder ORM（task_id FK、trigger_at aware UTC、job_id 派生标注）；DB CHECK + repository 双层闭集
3. **ReminderRepository**：create/get/list_for_task/list_scheduled/cancel_for_task/delete_for_task（FK-safe）/mark_fired/mark_cancelled——纯持久化
4. **reminder_policy.py（纯函数）**：三档（-1d/-2h/deadline）、MIN_LEAD_SECONDS=60 丢弃、quiet-hours 23-08 前向折叠、同分钟去重（优先级 day_before>hours_before>deadline）、deadline=None/非 pending → 零提醒
5. **ReminderService**：plan_reminders（**幂等**：cancel 旧 → 算 desired → persist facts → scheduler 重建）/cancel_for_task/resync_all（**跳过过期 trigger 不补发**、跳过 done/dismissed/deleted task）/fire（**重读最新状态**，非 pending 即 cancel 不投递）；delivery 注入边界（NoopDelivery 默认，M3 不宣称端用户 UX）
6. **ReminderScheduler（APScheduler 3.11 隔离）**：确定性 job_id `reminder:<id>`；**实测 3.11 replace_existing 会追加 → 显式 remove-then-add**；shutdown 容错 SchedulerNotRunningError；misfire_grace_time=1（3.11 拒绝 0）；startup 前可 add_job（resync → start 模式）
7. **TaskService 联动（ADR-006）**：create（pending+deadline → plan）/change_deadline（旧计划取消+新计划）/complete/dismiss（cancel）/delete（FK-safe hard-delete 先行）；**reminder_service 可选注入——禁用时 M2 行为不变**
8. **runtime 接线**：CAMPUSCUE_REMINDERS=1 启用；启动顺序 DB→repos→services→resync→scheduler.start；关闭 scheduler.shutdown(wait) 先于 DB dispose；失败路径逆序清理
9. **config**：ReminderConfig（enabled/min_lead/quiet_start/quiet_end，fail-fast 校验）
10. **pyproject**：+`apscheduler>=3.10,<4`

## 测试

- **344 passed**（+28 M3：schema 迁移 3/策略 8/service 10/resync 3/scheduler real 3/clock-timezone 2/gate 1）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso` + apscheduler 3.11.3）
- **本地真实调度器验收 PASS**（真实 APScheduler，无 QQ）：任务→3 facts/3 jobs → 重启 resync 重建无重复 → deadline 变更旧计划取消新计划 → complete 全取消 0 jobs 0 投递

## AGENT_DISCOVERED_DELTA（M3）

- [REPO_CONFIRMED] APScheduler 3.11 实测行为：memory jobstore replace_existing **追加**而非替换（→ 显式 remove-then-add）；shutdown 未启动调度器抛 SchedulerNotRunningError（→ 容错）；misfire_grace_time=0 被拒（→ 用 1）；AsyncIOScheduler 用真实墙钟（测试需真实 near-future deadline）
- [DESIGN_DECISION] schema v1→v2 owned migration（不引入 Alembic）；旧 M2a 测试"unsupported older version"措辞更新（v0 仍拒，v1 现合法迁移）
- 完整 Memory Delta 见 CHATGPT_MEMORY §9O

## REAL ENV

- M3 为 **LOCAL REAL SCHEDULER**（temp SQLite + 真实 APScheduler + FixedClock）；**无 QQ/NapCat 验收**（M3 不需要）
- 用户大号/QQ/NapCat 全程未触碰

## 下一步

- 外部 ChatGPT M3 源码复核（schema 迁移/DB fact vs scheduler derived/TaskService 集成/幂等/resync/missed reminder/Clock/timezone/runtime 生命周期/M2 回归/privacy）→ PASS 后 M4 授权

## 本轮修改文件

- 新增：src/campuscue/tasks/reminder_policy.py、src/campuscue/services/reminder_service.py、src/campuscue/services/reminder_scheduler.py、tests/integration/test_m3_reminders.py
- 修改：storage/{enums,models,database}.py（schema v2 + Reminder）、repositories/repositories.py（ReminderRepository + Task 变更原语）、services/task_service.py（生命周期联动）、app/runtime.py（接线）、config.py（ReminderConfig）、pyproject.toml（apscheduler）、tests/unit/test_m2a1_fixes.py（旧措辞）、Memory/handoff/README
