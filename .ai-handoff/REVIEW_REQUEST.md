# REVIEW_REQUEST.md

> M3（含 M3.1+M3.2）最终复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M3.2）复核本轮实现。

## 背景

M0-M2 全部 FINAL PASS。M3 实现完成（本地真实调度器验收 PASS）→ M3.1 硬化（6 项）→ M3.2 Final Gate Fix（3 项）。等待外部 M3 最终复核。

## 请求审核内容（M3 复核点，含 M3.1/M3.2）

1. **schema v1→v2 迁移安全**：前置验证（表/列）+ 迁移 SQL CHECK 约束与 fresh 对齐；**M3.2-B：schema_meta 恰一行是全局不变量——_precheck 版本分发前校验（[1,2] 与 [2,1] 均拒绝零变更，不依赖行序）**
2. **DB fact vs scheduler derived 不变式**：确定性 job_id `reminder:<id>`；resync 先 clear_all 真重建（同进程 stale 清理）
3. **quiet-hours 契约（M3.1-B + M3.2-A）**：canonical `is_inside_quiet_hours` 谓词；每个提醒同时满足 trigger<=deadline AND 不在 quiet 内 AND >=now+min_lead；clamp 目标 = quiet_start 前（默认 22:59:59）；overnight-only 契约（start>end fail-fast，quiet_end=0 合法）；边界测试（22:59:59/23:00:00/07:59:59/08:00:00）
4. **ReminderService 幂等**：重复 plan 无重复 facts/jobs
5. **TaskService 生命周期联动（ADR-006）**：create/change_deadline/complete/dismiss/delete 全收敛；可选注入（禁用时 M2 不变）
6. **composition-root 接线（M3.1-A + M3.2-C）**：ReminderPolicy 从 RuntimeConfig.reminders 构造（spy 生产构造器验证真实路径消费 timezone/min_lead/quiet）；无重复配置真值
7. **Clock/timezone**：FixedClock 注入；Asia/Shanghai + DST；trigger_at aware UTC
8. **默认投递安全（M3.1-F）**：默认 NoopDelivery；直接构造 fire 永不失败
9. **runtime 生命周期**：resync→start；shutdown→dispose；失败逆序清理；无 orphan 后台任务
10. **无 M4+ 实现 + privacy**：QQ/NapCat/用户账号未触碰；363 tests 全绿

## 验证层级

- **UNIT VERIFIED**：policy/repository/service 生命周期（47 个 M3 系列测试）
- **INTEGRATION VERIFIED**：363 tests 全量 + fresh venv isolation + Anti-AstrBot
- **LOCAL REAL SCHEDULER VERIFIED**：真实 APScheduler 3.11（facts/jobs 一致性、重启 resync、deadline 变更、complete 0 投递）
- **REAL QQ/NapCat**：NOT RUN（M3 不需要；M2b.2 REAL ENV 保留）

## 风险与未验证项（诚实声明）

- 端用户投递 UX 未实现（delivery 注入边界 + NoopDelivery）
- APScheduler 用真实墙钟（AsyncIOScheduler 内部）；ReminderService 业务时间用注入 Clock——分离设计
- quiet 窗为 overnight-only 契约（同日窗口显式拒绝——产品只要求 23-8，YAGNI）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
