# REVIEW_REQUEST.md

> M3 Reminder 源码复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M3）复核本轮实现。

## 背景

M0-M2 全部 FINAL PASS（含 M2b.2 REAL ENV）。M3 Reminder authorized。本轮实现完成，等待外部复核。

## 请求审核内容（10 项 M3 复核点）

1. **schema v1→v2 迁移安全**：`SCHEMA_VERSION=2`；v1 DB（含任务数据）→ owned migration（建 reminders 表 + version bump，数据保留）；v2 幂等重开；v0/更新/未知版本 → SchemaRefusedError 零变更（测试证明 DB 字节不变）
2. **DB fact vs scheduler derived 不变式**：reminders 行 = canonical facts；APScheduler jobs = 派生（resync_all 从 facts 重建）；确定性 job_id `reminder:<id>`
3. **ReminderService 幂等**：重复 plan_reminders → 无重复 facts/jobs（旧 facts cancel + 新 facts 安装，job 数恒 3）
4. **TaskService 生命周期联动（ADR-006）**：create→plan；change_deadline→旧取消+新计划；complete/dismiss→cancel；delete→FK-safe hard-delete 先行；reminder_service 可选注入（禁用时 M2 行为不变）
5. **resync 重建**：重启从 facts 重建无重复；停机错过（trigger<=now）→ cancel 不补发；done/dismissed/deleted task → 不复活
6. **Clock/timezone**：无隐藏墙钟；FixedClock 注入；Asia/Shanghai + DST（America/New_York）边界测试；trigger_at 存 aware UTC
7. **APScheduler 3.11 隔离**：framework 专属代码在 reminder_scheduler.py；ReminderService 只见 ReminderSchedulerBoundary；实测修复：replace_existing 追加→显式 remove-then-add；SchedulerNotRunningError 容错；misfire_grace_time>0
8. **runtime 生命周期**：启动 DB→repos→services→resync→scheduler.start；关闭 scheduler.shutdown(wait) 先于 DB dispose；失败逆序清理；无 orphan 后台任务
9. **M2 回归**：Reminder 子系统禁用时 task pipeline 完整工作（可选注入边界）；344 tests 全绿
10. **无 M4+ 实现 + privacy**：无 Agent/Tool/API/WebUI；QQ/NapCat/用户账号全程未触碰

## 验证层级（明确区分）

- **UNIT VERIFIED**：policy 纯函数、repository、service 生命周期（28 个 M3 测试）
- **INTEGRATION VERIFIED**：344 tests 全量回归 + fresh venv isolation + Anti-AstrBot
- **LOCAL REAL SCHEDULER VERIFIED**：真实 APScheduler 3.11 验收（任务→3 facts/3 jobs；重启 resync 重建无重复；deadline 变更；complete 全取消 0 投递 0 jobs）
- **REAL QQ/NapCat**：NOT RUN（M3 明确不需要；M2b.2 REAL ENV 证据保留）

## 风险与未验证项（诚实声明）

- 端用户投递 UX 未实现（M3 = 调度/生命周期里程碑；delivery 注入边界 + NoopDelivery；QQ/桌面通知为后续）
- APScheduler 用真实墙钟（AsyncIOScheduler 内部）；ReminderService 业务时间用注入 Clock——两者分离（测试用真实 near-future deadline 验证真触发）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
