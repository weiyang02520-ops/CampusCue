# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M3.1 Reminder Hardening）

- **本轮**：外部 ChatGPT 对 M3 复核 = PASS_WITH_FIXES（6 项 finding A-F），执行硬化修复轮
- **状态**：M3 = HARDENING_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M3 FINAL = NOT YET DECLARED；M4 = NOT_AUTHORIZED**

## 本轮完成（M3.1）

1. **[A] Reminder runtime config 接线**：`CampusRuntime` 从 `RuntimeConfig.reminders` 构造 `ReminderPolicy`（timezone/min_lead_seconds/quiet_start/quiet_end 真实被消费，不再用 tasks.timezone + 默认 policy）；删除 `TaskPipelineConfig.reminders_enabled` 重复真值（唯一真值在 ReminderConfig）；测试通过真实 `load_config` 验证 runtime-consumed policy
2. **[B] quiet-hours 绝不超过 deadline**：硬不变量 `trigger_at_utc <= task.deadline`——前向折叠超过 deadline → clamp 到 quiet_end-1s 同日（仍 < deadline）或丢弃该 intent；防御性第二道检查在 discard 阶段；测试：23:59 deadline（无 post-deadline）、凌晨 deadline（quiet 内）、fold-clamp 场景、DST（NY）场景更新
3. **[C] resync 真重建**：`resync_all` 先 `scheduler.clear_all()` 再加载 facts 重建——同进程 stale job 不可能存活；测试：注入 stale job `reminder:9999` + task done → resync 后 stale 消失、仅 canonical jobs 保留
4. **[D] v1 迁移前 schema 验证**：`_validate_v1_schema`——必需表齐全 + schema_meta **恰一行** + 各表关键列存在；malformed/任意 SQLite 带 schema_meta=1 → SchemaRefusedError 零变更；测试：malformed tasks 表拒绝（字节不变）、多行 schema_meta 拒绝（零变更）
5. **[E] 迁移约束对齐**：迁移 SQL 的 reminders 表加 CHECK（type/status 闭集）与 fresh ORM v2 完全一致；测试：v1→v2 后直接非法 INSERT（invalid type/status）被 SQLite 拒绝
6. **[F] 默认投递安全**：`ReminderService.__init__` 默认 `_delivery = NoopDelivery()`（直接构造 + fire 永不失败）；测试：不调 set_delivery 直接 fire → 成功 fired

## 测试

- **354 passed**（+10 M3.1）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`，354）
- 无 QQ/NapCat（M3 不需要）

## AGENT_DISCOVERED_DELTA（M3.1）

- [DESIGN_CHANGE]：DST 测试语义更新——deadline 落在 quiet hours 时 deadline intent 被 post-deadline 不变量丢弃（行为变更，非 bug）
- [REPO_CONFIRMED]：schema_meta.schema_version 有 UNIQUE 约束，"多行冲突"测试需用不同 version 值构造
- Memory Delta 见 CHATGPT_MEMORY §9P（4 条 M3_FINDING）

## REAL ENV

- M3/M3.1 为 LOCAL REAL SCHEDULER（无 QQ）；M2b.2 REAL ENV 保留；用户 QQ/NapCat 未触碰

## 下一步

- 外部 ChatGPT M3（含 M3.1）复核 → M3 FINAL PASS → M4 授权

## 本轮修改文件

- 修改：app/runtime.py（policy 接线）、config.py（去 reminders_enabled）、tasks/reminder_policy.py（post-deadline 不变量 + clamp）、services/reminder_service.py（resync clear_all + 默认 NoopDelivery）、storage/database.py（_validate_v1_schema + 迁移 CHECK）
- 新增：tests/integration/test_m31_hardening.py（10 tests）
- 修改：tests/integration/test_m3_reminders.py（DST 语义更新）、Memory/handoff
