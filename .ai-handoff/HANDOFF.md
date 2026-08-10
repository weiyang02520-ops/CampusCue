# HANDOFF.md

> 当前操作状态（canonical）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY。

## 当前（M2a.1 Foundation Correctness Fix）

- **本轮**：修复外部源码审核 6 项 finding（M2a.1 A-F + 15/16/17）
- **状态**：M2a FOUNDATION_FIX_COMPLETE — AWAITING_EXTERNAL_REVIEW
- **Gate**：M0/M1/M1.3 = PASS；**M2 = IN_PROGRESS（M2a 修复完成待复核；M2b NOT_AUTHORIZED）**

## 本轮完成（finding 对照）

| # | Finding | 修复 |
|---|---|---|
| A | Provider.test() 缺 LLMMessage import（NameError）+ 无真实路径测试 | 修 import；回归测试走真实链（manager.get_default → provider.test → chat → MockTransport → parse）；test_default 经 get_default 真实路径 |
| B | LLMRequest.timeout_s 无效 | 契约生效：request override > provider 默认；LLMRequest.timeout_s=None 默认；httpx 请求 timeout 传入（contract 测试断言 extensions.timeout） |
| 5 | 数值校验 | validate_provider_numeric：timeout_s/max_tokens/max_context_tokens >0；temperature ≥0 有限数 |
| C | 闭集枚举未强制 | repository 边界 _require_enum 显式拒绝非法值（status/category/priority/extraction status）；**DB CHECK 约束**双层防御（tasks 3 条 + extractions 1 条 + provider timeout） |
| D | schema 兼容检查先于变更（不兼容 DB 被改写） | **先只读预检（sqlite3 ro）→ 拒绝 → 零变更**；无 schema_meta 但有用户表 → SchemaRefusedError 拒绝认领；版本不匹配拒绝 |
| E | Clock 抽象死代码 | repository 显式 clock.utcnow() 设置 created_at/updated_at（SystemClock/FixedClock 注入；naive 拒绝） |
| F | secret_reference 校验太晚 | providers/validation.py 共享校验（配置 + Provider 运行时同一规则）；repository 持久化前拒绝；bootstrap 假 --replace claim 修正 |
| 15 | ProviderManager 无 get_by_id | 新增 get_by_id + NotFound 测试 |
| 16 | 成功响应过宽松 | 严格解析：choices 存在/非空、message 是 dict、content 存在且是 str，否则 MALFORMED_OUTPUT |
| 17 | 状态分类依赖 JSON body | 状态码先分类（401/403→AUTH、429→RATE_LIMIT、5xx→SERVER_ERROR 不读 body）；400 安全解析细分；200 非 JSON→MALFORMED |

## 测试

- **186 passed**（新增 47：test_m2a1_fixes.py；含 schema 零变更 6 项、时钟注入 3 项、枚举拒绝 6 项、timeout 契约 4 项、严格解析 6 项、状态先分类 6 项）
- package isolation PASS（fresh venv 含 DB smoke）；Anti-AstrBot PASS

## AGENT_DISCOVERED_DELTA（M2a.1）

- [STORAGE_FACT]：sqlite 系统表 sqlite_sequence/sqlite_stat* 需从"未知表"判断中排除（预检已处理）
- [PROVIDER_FACT]：httpx 将 timeout 展开为 per-phase dict（extensions.timeout）；断言用 ["read"]
- [PROVIDER_FACT]：LLMRequest.timeout_s 默认改为 None（避免遮蔽 provider 配置）
- [TEST_FACT]：fixture 跨文件不共享（db_session_factory_raw 独立定义）
- [DESIGN_CONFLICT]：DB CHECK 约束 + repository 双层校验已确认是 M2 默认防御（无迁移框架）

## REAL ENV

- M1 REAL ENV VERIFIED 保留；M2a.1 无新 REAL ENV 声明

## 本轮修改文件

- 修改：providers/openai_compatible.py（A/B/5/16/17）、providers/models.py（timeout None 默认）、providers/manager.py（get_by_id）、providers/validation.py（新增）、repositories/repositories.py（枚举/校验/Clock）、storage/database.py（预检零变更）、storage/models.py（CHECK 约束）、scripts/m2_configure_provider.py（假 claim）
- 新增：tests/unit/test_m2a1_fixes.py（47 tests）
- 修改：双 Memory（§9G + 失败模式）、.ai-handoff/ 6 文件

## 下一步

- 外部 ChatGPT 复核 M2a.1（12 项审核点见 REVIEW_REQUEST）→ M2b 授权
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
