# 09_STORAGE.md

> 存储设计（M2 实现，M5 schema v3 完善）。**DB = 唯一业务事实源**。

## 技术选型

- SQLite + SQLAlchemy（SQLModel 风格，与 V1 一致的经验保留）
- 单文件数据库（如 `data/campuscue.db`），数据目录与代码分离，gitignore
- WAL 模式 + `busy_timeout`（参考 AstrBot/V1 对 SQLite 写锁的处理：**async 不等于无并发写**，必须处理写锁）
- 迁移：第一版用轻量方案（`create_all` + 版本表/手工迁移脚本），不引入 Alembic（YAGNI；出现真实迁移需求再评估）
- 当前 schema：**v3**（M5）——v1→v2 加 reminders；v2→v3 加 `settings` 表、`sources.deleted_at`（软删除）、M5 查询索引。迁移保持 atomic（BEGIN IMMEDIATE / COMMIT / ROLLBACK）。

## 表（草案，M2 定稿）

| 表 | 关键字段 | 说明 |
|---|---|---|
| sources | id, platform, conversation_id(uniq), name, enabled, auto_extract, context_window, privacy_policy, created_at, updated_at | 来源 |
| tasks | id, title, description, category, course, deadline(aware UTC), status, priority, confidence, dedup_key(idx), source_id, source_message_id, source_text_reference, created_at, updated_at | 任务 |
| extractions | id, source_message_id, raw_result, normalized_result, confidence, provider, model, status, error, created_at | 抽取审计 |
| reminders | id, task_id(fk), trigger_at, type, status, last_run, error, job_id(派生) | 提醒事实 |
| provider_configs | id, name, provider_type, base_url, model, temperature, max_tokens, max_context_tokens, timeout_s, secret_reference, enabled | Provider（只存 secret_reference 环境变量名，ADR-012-F） |
| settings | key(uniq), value(JSON) | 全局设置（M2a 未实现，YAGNI 延后） |

## 并发模型（AstrBot/V1 教训）

- 每个 repository 方法独立短事务（`async with session.begin()`）
- 写路径串行化：单进程内 SQLite 写用事务 + busy_timeout（如 30s）；需要时引入全局写锁（简单 asyncio.Lock 包 TaskService 写操作，第一版够用）
- 不做连接池/多进程写（第一版单进程）

## Repository / Service 分层

```
storage/database (engine + session factory)
  → repositories: TaskRepository / SourceRepository / ExtractionRepository / ReminderRepository / ProviderConfigRepository / SettingRepository
  → services: TaskService / ReminderService / NotificationService（M4: ProviderService）
  → 消费方: API / Agent Tool / Task Pipeline / Reminder / Adapter
```

**激活**（J 修正）：SourceRepository / ExtractionRepository / TaskRepository 随 M2 实现（Task Pipeline 依赖）；ReminderRepository 随 M3；ProviderConfigRepository 随 M2a（Provider Foundation）。

**规则（V1 教训）**：
- 消费方只能调 Service，不能绕过 Repository 直接开 session 写表
- Service 是唯一知道"业务不变式"的地方（如：deadline 变化必须重建提醒）
- Repository 只做单表 CRUD + 查询，不做业务

## Source of Truth 声明

| 数据 | 事实源 | 派生 |
|---|---|---|
| 任务状态 | tasks 表 | WebUI store / SSE 载荷 |
| 提醒计划 | reminders 表 | APScheduler jobs（重启重建） |
| 抽取记录 | extractions 表 | 消息页渲染 |
| Provider 配置 | provider_configs 表 | Runtime 内存实例 |
| 消息正文 | 仅被识别任务的来源消息（见下） | — |

## 消息保留（隐私，见 14_SECURITY_PRIVACY）

- 默认**不保存完整群聊全文**
- 保存：被识别为候选/创建任务的消息原文（source_text_reference，保留可核对）+ 抽取记录
- 配置项：保留时长（如 30/90/365 天），到期清理
- `messages` 表视 M5 需求再定（第一版可无此表，消息页数据来自 extractions + tasks.source_text_reference）

## 备份 / 恢复（REUSE_BEHAVIOR from V1 backup.py/transfer.py）

- backup v1 格式：全部业务表单事务原子导出；**明确排除**：API Key、QQ 登录态、NapCat 文件、平台凭据、运行时状态
- restore：`confirm_replace` 确认 + 版本/格式/枚举/重复身份校验 → 单事务替换 → 成功后 resync 提醒
- transfer 格式（导入导出）：只带任务，排除 remind 运行时字段；导入后由 deadline 重推提醒；dedup_key 重算
