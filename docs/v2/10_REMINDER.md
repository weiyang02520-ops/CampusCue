# 10_REMINDER.md

> Reminder 服务设计（M3 实现）。核心思想（参考 AstrBot cron/manager 并已由 V1 验证）：**DB Reminder = Fact，APScheduler = Runtime Derived State**。

## 架构

```
tasks (DB) ──resync──► reminders (DB) ──schedule──► APScheduler (派生)
                                   ▲                     │
                                   └───── fire ─────────┘
                                          │
                                     NotificationService
```

- `reminders` 表是事实源（task_id、trigger_at、type、status）
- APScheduler job 只是运行时派生物：重启后从 DB 全量重建（resync）
- 任何"重建"操作幂等（job_id 固定 + replace_existing）

## 排期规则（REUSE_BEHAVIOR from V1）

- 三档默认：截止前 1 天、截止前 2 小时、截止时刻（profile.lead_minutes 可调）
- quiet-hours（如 23:00-8:00 不打扰）→ 折叠到最近允许时刻，同分钟去重
- 距调度点 < 60s 的提醒丢弃（MIN_LEAD_SECONDS）
- deadline 为 None → 不排提醒（待确认任务不排）

## 触发行为

- fire 时：重读任务最新状态（已 complete/dismissed/deleted → 跳过，防"完成仍提醒"）
- 推送目标：用户配置的目标会话（V1：不回源群，避免打扰群成员）
- Windows 桌面 toast（V1 notify.py 已验证的 PowerShell+WinRT 方式保留为可选项）

## 生命周期联动（全部幂等）

| 事件 | 动作 |
|---|---|
| task created（有 deadline） | plan_reminders → add_job（先 cancel 再排） |
| task deadline 修改 | 取消旧 job → 重排 |
| task complete / dismiss / delete | 取消该 task 所有 job |
| 程序启动 | resync_all：从 tasks 全量重建（V1 已验证：重启后正确恢复并清理过期 job） |
| 程序运行中任务被手工改 DB（外部导入） | 导入后触发 resync 或逐任务重建 |

## 防重复提醒（V1 已验证的 5 道防线，全部保留）

1. `schedule_for_task` 先 cancel 再排（幂等）
2. fire 时重读任务，非 active 即跳过
3. quiet-hours 折叠去重
4. MIN_LEAD_SECONDS 丢弃
5. job 不持久化（重启即死）+ resync 保证可推导

## 时区

- trigger_at 存 aware UTC（与 tasks.deadline 一致）
- 调度器按任务所属 profile 时区计算触发时刻
- 测试：固定时钟 + 固定时区注入（禁 datetime.now() 直用）

## 验收（M3 PASS 标准）

- 重启恢复：kill → 重启 → reminders 与 job 完整重建，无重复 job
- deadline 更新：旧 job 消失，新 job 就位（DB 层验证 job 数 = 预期）
- complete：job 取消，到点不提醒
- delete：job 清理
- 幂等：同一 task 重复 plan 不产生重复 job
- 错过执行时间（程序停机期间到期）：启动 resync 时不补发过期提醒（misfire_grace_time=0 或检查 trigger_at < now 则跳过）
