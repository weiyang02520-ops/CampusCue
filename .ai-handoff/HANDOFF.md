# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M3.4 Storage Safety Final Seal）

- **本轮**：外部 ChatGPT 对 M3.3 复核 = PASS；M3 FINAL = CHANGES_REQUESTED——2 个存储安全 blocker（A 原子迁移 / B 完整列验证）
- **状态**：M3 = STORAGE_SAFETY_FINAL_SEAL_COMPLETE_AWAITING_EXTERNAL_REVIEW；**M3 FINAL = NOT YET DECLARED；M4 = NOT_AUTHORIZED**

## 本轮完成（M3.4）

1. **[A] 原子迁移**：`_migrate_v1_to_v2` 改为单显式事务——`BEGIN IMMEDIATE` + 逐条 `execute()`（CREATE TABLE reminders / 2 个索引 / UPDATE schema_meta）+ `COMMIT`；任何异常 `ROLLBACK`。**不用 executescript**（其隐式事务控制可提交挂起事务）。测试：预置冲突索引名强制 CREATE INDEX 失败 → 迁移抛错、schema_version 仍 1、无 reminders 表/索引残留、原 v1 表完整
2. **[A2] 半迁移 v1 拒绝**：schema_meta=1 且已含 reminders（M3-only 结构）→ SchemaRefusedError "half-migrated/partial"，字节不变零变更（不猜测/不修复）
3. **[B] 完整列契约验证**：`_COMMON_TABLE_COLUMNS` + `_REMINDER_COLUMNS`——v1/v2 manifest 覆盖**全部 ORM 必需列**（非子集）：tasks 含 source_message_id/created_at/updated_at/description 等 15 列；reminders 含 last_run/error/job_id 等 10 列；provider_configs 含 timeout_s/secret_reference 等 13 列。测试：v2 缺 source_message_id/job_id/timeout_s → 拒绝零变更；v1 截断表 → 拒绝零变更

## 测试

- **378 passed**（+8 M3.4：原子回滚 1/干净迁移 1/半迁移 1/完整列 5）；Anti-AstrBot PASS；package isolation PASS（`.venv-m2iso`，378）
- M3 系列 62 个测试全绿（旧测试 v1/v2 构造器列集完整，未破坏）

## AGENT_DISCOVERED_DELTA（M3.4）

- [REPO_CONFIRMED]：sqlite3 `executescript` 隐式事务控制危险 → 用 `isolation_level=None` + 显式 BEGIN IMMEDIATE/COMMIT/ROLLBACK
- [REPO_CONFIRMED]：完整列 manifest 从 ORM model 推导（非手写子集）；v1/v2 共享 _COMMON_TABLE_COLUMNS
- Memory Delta 见 CHATGPT_MEMORY §9S（2 条 DATA_SAFETY + DESIGN_DECISION）

## REAL ENV

- M3 系列均为 LOCAL REAL SCHEDULER（无 QQ）；M2b.2 REAL ENV 保留；用户 QQ/NapCat 未触碰

## 下一步

- 外部 ChatGPT M3 最终复核（含全部修复轮）→ M3 FINAL PASS → M4 授权

## 本轮修改文件

- 修改：storage/database.py（原子迁移 + 半迁移拒绝 + 完整列 manifest）
- 新增：tests/integration/test_m34_storage_seal.py（8 tests）
- 修改：Memory（双）、.ai-handoff/（HANDOFF/PROJECT_STATE/STATUS/REVIEW_REQUEST/CHANGELOG）
