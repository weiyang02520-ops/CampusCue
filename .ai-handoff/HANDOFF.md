# HANDOFF.md

> 当前操作状态（canonical）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY。

## 当前（M2a Data & Provider Foundation）

- **本轮**：实现 M2a（数据层 + Provider 基础），供 M2b Task Pipeline 使用
- **状态**：M2a DATA_PROVIDER_FOUNDATION_COMPLETE — AWAITING_EXTERNAL_REVIEW
- **Gate**：M0/M1/M1.3 = PASS；**M2 = IN_PROGRESS（M2a 完成待复核；M2b NOT_AUTHORIZED）**

## 本轮完成

1. **ADR-012**（M2 数据/Provider 契约锁定）：TaskStatus 唯一枚举（pending_confirm/pending/done/dismissed）、Source 身份 (platform, conversation_id)、L2 上下文=临时内存 ring buffer、Provider 默认=恰好一个 enabled、secret_reference 只存环境变量名、UTC 存储 + naive 拒绝
2. **storage/**：SQLAlchemy 2.x + aiosqlite；Database（engine/pragma FK+WAL+busy_timeout/schema_meta 版本检查：空库创建、重开、未知版本拒绝）；UTCDateTime TypeDecorator；models（sources/tasks/extractions/provider_configs/schema_meta；显式无 reminders/messages/settings）
3. **repositories/**：Source/Task/Extraction/ProviderConfig（单表 CRUD 原语；DuplicateError/NotFoundError；task 唯一约束 (source_id, source_message_id) 防并发重复）
4. **services/**：SourceService（create/enable/disable/auto_extract/身份查找 + 校验）
5. **providers/**：BaseProvider / LLMRequest（无 Tool 依赖）/ LLMResponse / ProviderError taxonomy（9 类）/ OpenAICompatibleProvider（httpx、URL 规范化、Bearer 可选、json_schema structured output、错误分类）/ ProviderManager（0/1/>1 enabled 语义）/ scripts/m2_configure_provider.py（临时 bootstrap，M5 替换）
6. **测试**：storage 29 + provider 23 = 52 新增；**全量 139 passed**；package isolation PASS（fresh venv 含 DB smoke）；Anti-AstrBot PASS

## 关键设计事实（AGENT_DISCOVERED_DELTA）

- [STORAGE_FACT]：SQLite 不保留 tzinfo → UTCDateTime TypeDecorator 统一 UTC 存储/读取 aware（ADR-012-G）；naive 在 bind 时拒绝
- [STORAGE_FACT]：CAMPUSCUE_ENV=test 且无显式 DB 路径 → Database 构造即 FAIL（M2 硬隔离门）
- [PROVIDER_FACT]：disable_thinking 是 provider-neutral intent，不猜测厂商 wire 字段（M2 §33）；json_schema 结构输出已 CONTRACT VERIFIED（响应体含 response_format.json_schema）
- [PROVIDER_FACT]：secret_reference 格式正则校验（^[A-Z][A-Z0-9_]{2,63}$）；secret 值永不进 DB（有测试证明）
- [REPO_FACT]：fresh venv 安装后 import storage/provider 模块 + DB 冒烟通过（不依赖 Legacy/AstrBot）
- [UNVERIFIED_HYPOTHESIS]：真实 Provider 端点（如 Ark）的 json_schema 支持度——M2b 真实验收时确认

## REAL ENV

- **M1 REAL ENV VERIFIED 保留**（2026-08-10，NapCat v4.18.18 + 真实 QQ）
- M2a **无新 REAL ENV 声明**（纯基础层；真实 Provider 验收留 M2b）

## 历史摘要（详情见 CHANGELOG_AI.md）

| Milestone | 状态 |
|---|---|
| M0 / M0.1 / M0.2 / M1 / M1.1 / M1.2 / M1.3 | 全部 PASS（commit 见 Git history） |
| M2a | 本轮（Data + Provider Foundation） |

## 本轮修改文件

- 新增：v2/src/campuscue/storage/{enums,models,database,clock}.py、repositories/repositories.py、services/source_service.py、providers/{base,models,errors,openai_compatible,manager}.py、scripts/m2_configure_provider.py、tests/integration/test_storage.py、tests/unit/test_provider.py、docs/v2/adr/ADR-012_M2_DATA_AND_PROVIDER_CONTRACTS.md
- 修改：v2/pyproject.toml（+sqlalchemy/aiosqlite/httpx）、docs/v2/{06,09,17,18}、v2/README.md、双 Memory、.ai-handoff/ 6 文件

## 下一步

- 外部 ChatGPT 复核 M2a（15 项审核点见 REVIEW_REQUEST）→ M2b 授权
