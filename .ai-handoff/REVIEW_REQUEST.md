# REVIEW_REQUEST.md

> M3（含 M3.1+M3.2+M3.3）最终复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M3.3）复核本轮实现。

## 背景

M0-M2 全部 FINAL PASS。M3 实现 + M3.1 硬化 + M3.2 Final Gate Fix 均通过外部复核；M3.3 修复最终对账缺口。等待外部 M3 最终复核。

## 请求审核内容（M3 复核点，含全部修复轮）

1. **schema v1→v2 迁移安全**：前置验证（表/列/schema_meta 恰一行）+ 迁移 SQL CHECK 约束对齐；**M3.3-B：当前 v2 DB create_all 前只读结构验证**（缺 reminders 表/缺 tasks 关键列 → SchemaRefusedError 零变更）
2. **DB fact vs scheduler derived 不变式**：确定性 job_id；resync 先 clear 真重建
3. **resync 真业务对账（M3.3-A）**：Tasks→facts→jobs；迁移回填（v1 旧任务启动后获提醒）；崩溃间隙治愈（Task commit 成功但 reminders 缺失）；部分对账（保留匹配 fact 身份、只创建缺失、只取消 stale）；幂等（unchanged restart 同 fact IDs、无 cancelled 历史增长）；不补发
4. **quiet-hours 契约**：canonical 谓词；trigger<=deadline AND 不在 quiet AND >=now+min_lead；overnight-only 契约
5. **TaskService 生命周期联动（ADR-006）**：create/change_deadline/complete/dismiss/delete 全收敛；可选注入
6. **composition-root 接线**：ReminderPolicy 从 RuntimeConfig 构造（spy 生产构造器验证）
7. **Clock/timezone**：FixedClock 注入；Asia/Shanghai + DST；aware UTC
8. **默认投递安全**：默认 NoopDelivery
9. **runtime 生命周期**：resync→start；shutdown→dispose；失败逆序清理
10. **无 M4+ 实现 + privacy**：QQ/NapCat/用户账号未触碰；370 tests 全绿；17_MILESTONES 一致

## 验证层级

- **UNIT VERIFIED**：policy/repository/service 生命周期（54 个 M3 系列测试）
- **INTEGRATION VERIFIED**：370 tests 全量 + fresh venv isolation + Anti-AstrBot
- **LOCAL REAL SCHEDULER VERIFIED**：真实 APScheduler 3.11（facts/jobs 一致性、重启 resync、deadline 变更、complete 0 投递）
- **REAL QQ/NapCat**：NOT RUN（M3 不需要；M2b.2 REAL ENV 保留）

## 风险与未验证项（诚实声明）

- 端用户投递 UX 未实现（delivery 注入边界 + NoopDelivery）
- APScheduler 用真实墙钟（AsyncIOScheduler 内部）；ReminderService 业务时间用注入 Clock——分离设计
- quiet 窗为 overnight-only 契约（同日窗口显式拒绝——YAGNI）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
