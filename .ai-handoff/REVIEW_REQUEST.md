# REVIEW_REQUEST.md

> M3（含 M3.1-M3.4）最终复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M3.4）复核本轮实现。

## 背景

M0-M2 全部 FINAL PASS。M3 实现 + M3.1 硬化 + M3.2 Final Gate Fix + M3.3 Recovery Fix 均通过外部复核；M3.4 完成存储安全最终封印。等待外部 M3 最终复核。

## 请求审核内容（M3 复核点，含全部修复轮）

1. **原子 v1→v2 迁移（M3.4-A）**：单显式事务（BEGIN IMMEDIATE + 逐条 execute + COMMIT；异常 ROLLBACK）——强制中途失败（冲突索引）→ schema_version 仍 1、无 reminders 表/索引残留、原 v1 完整；干净 v1 迁移仍成功
2. **半迁移 v1 拒绝（M3.4-A2）**：schema_meta=1 + reminders 已存在 → REFUSE 零变更（字节不变）
3. **完整列契约验证（M3.4-B）**：v1/v2 manifest 覆盖全部 ORM 必需列（非子集）——tasks 缺 source_message_id/created_at、reminders 缺 job_id、provider_configs 缺 timeout_s、v1 截断表 → 全部 REFUSE 零变更；valid v1 迁移 + valid v2 重开 PASS
4. **schema_meta 全局恰一行**：_precheck 版本分发前校验（[1,2]/[2,1] 拒绝零变更）
5. **resync 真业务对账（M3.3-A）**：Tasks→facts→jobs；迁移回填/崩溃修复/部分对账/ID 稳定/无 churn/不补发
6. **quiet-hours 契约**：canonical 谓词；trigger<=deadline AND 不在 quiet AND >=now+min_lead；overnight-only
7. **TaskService 生命周期联动（ADR-006）**：create/change_deadline/complete/dismiss/delete 全收敛；可选注入
8. **composition-root 接线 + Clock/timezone + 默认 NoopDelivery**
9. **runtime 生命周期**：resync→start；shutdown→dispose；失败逆序清理
10. **无 M4+ 实现 + privacy**：QQ/NapCat/用户账号未触碰；378 tests 全绿；文档一致

## 验证层级

- **UNIT VERIFIED**：policy/repository/service 生命周期（62 个 M3 系列测试）
- **INTEGRATION VERIFIED**：378 tests 全量 + fresh venv isolation + Anti-AstrBot
- **LOCAL REAL SCHEDULER VERIFIED**：真实 APScheduler 3.11（facts/jobs 一致性、重启 resync、deadline 变更、complete 0 投递）
- **REAL QQ/NapCat**：NOT RUN（M3 不需要；M2b.2 REAL ENV 保留）

## 风险与未验证项（诚实声明）

- 端用户投递 UX 未实现（delivery 注入边界 + NoopDelivery）
- APScheduler 用真实墙钟（AsyncIOScheduler 内部）；ReminderService 业务时间用注入 Clock——分离设计
- quiet 窗为 overnight-only 契约（同日窗口显式拒绝——YAGNI）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
