# REVIEW_REQUEST.md

> M3（含 M3.1 硬化）最终复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M3.1）复核本轮实现。

## 背景

M0-M2 全部 FINAL PASS。M3 Reminder 实现完成（本地真实调度器验收 PASS），外部复核 = PASS_WITH_FIXES（6 项）。本轮 M3.1 硬化全部落地。

## 请求审核内容（10 项 M3 复核点）

1. **schema v1→v2 迁移安全**：v1 DB → owned migration（数据保留）；**M3.1-D 前置验证**（必需表/关键列/schema_meta 恰一行）——malformed/任意 SQLite 带 schema_meta=1 → SchemaRefusedError 零变更（字节不变测试）；**M3.1-E 约束对齐**：迁移 SQL CHECK（type/status 闭集）与 fresh v2 一致（非法 INSERT 被 SQLite 拒绝）
2. **DB fact vs scheduler derived 不变式**：reminders 行 = canonical；jobs = 派生（确定性 job_id `reminder:<id>`）
3. **ReminderService 幂等**：重复 plan 无重复 facts/jobs
4. **TaskService 生命周期联动（ADR-006）**：create/change_deadline/complete/dismiss/delete 全收敛；可选注入（禁用时 M2 不变）
5. **resync 真重建（M3.1-C）**：先 clear_all 再加载 facts——同进程 stale job 消失（注入 stale job 测试）；停机错过不补发
6. **quiet-hours 不超 deadline（M3.1-B）**：硬不变量 trigger <= task.deadline；fold 超限 → clamp（quiet_end-1s 同日）或丢弃；23:59/凌晨/DST 测试
7. **runtime config 接线（M3.1-A）**：ReminderPolicy 从 RuntimeConfig.reminders 构造（timezone/min_lead/quiet 真被消费）；无重复配置真值（tasks.reminders_enabled 已删）
8. **Clock/timezone**：FixedClock 注入；Asia/Shanghai + DST；trigger_at aware UTC
9. **默认投递安全（M3.1-F）**：直接构造 + fire 永不失败（默认 NoopDelivery）；不宣称端用户 UX
10. **无 M4+ 实现 + privacy**：QQ/NapCat/用户账号未触碰；354 tests 全绿

## 验证层级

- **UNIT VERIFIED**：policy/repository/service 生命周期（38 个 M3+M3.1 测试）
- **INTEGRATION VERIFIED**：354 tests 全量 + fresh venv isolation + Anti-AstrBot
- **LOCAL REAL SCHEDULER VERIFIED**：真实 APScheduler 3.11（facts/jobs 一致性、重启 resync、deadline 变更、complete 0 投递）
- **REAL QQ/NapCat**：NOT RUN（M3 不需要；M2b.2 REAL ENV 保留）

## 风险与未验证项（诚实声明）

- 端用户投递 UX 未实现（delivery 注入边界 + NoopDelivery）
- APScheduler 用真实墙钟（AsyncIOScheduler 内部）；ReminderService 业务时间用注入 Clock——分离设计

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
