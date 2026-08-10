# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2a.2 Final Foundation Cleanup）

- **本轮**：修复外部审核最终 7 项 finding（A-G）
- **状态**：M2a FOUNDATION_COMPLETE — AWAITING_EXTERNAL_FINAL_REVIEW
- **Gate**：M0/M1/M1.3 = PASS；**M2 = IN_PROGRESS（M2a+M2a.1+M2a.2 完成待复核；M2b NOT_AUTHORIZED）**

## 本轮完成（finding 对照）

| # | Finding | 修复 |
|---|---|---|
| A | secret_reference 校验仍重复（openai_compatible 本地 _ENV_NAME_RE） | 删除本地正则；Provider 构造 + 运行时 `_resolve_secret` 均调 validation.py 的 validate_secret_reference（ValueError → ProviderError INVALID_REQUEST） |
| B | ProviderConfigRepository 可持久化非法数值 | validation.py 新增 validate_provider_config_numeric（finite/>0/正 int 拒 bool/温度≥0）；repository 持久化前调用；NaN/±inf 拒 |
| C | LLMRequest override 绕过校验 | chat() 边界 validate_request_override（timeout/max_tokens/temperature）→ 非法即 ProviderError，**无传输调用**（测试断言 called==[]） |
| D | ORM 隐藏墙钟默认 | storage/models.py 删除 _utcnow/_aware_utc 与 default/onupdate；created_at/updated_at required（NOT NULL 无默认）；直接 ORM insert 无时间戳 → 失败 |
| E | HANDOFF append-only 复发 | 本文件重写为单一 canonical（历史进 CHANGELOG/Git） |
| F | PROJECT_STATE 内部腐烂 | 全语义修复（见下） |
| G | Memory/失败模式 | 双 Memory §9H + AGENT_MEMORY 新失败模式（HANDOFF relapse / PROJECT_STATE rot） |

## 测试

- **203 passed**（新增 17：test_m2a2_fixes.py——repository 数值拒绝 5 组（含 NaN/Inf/bool）+ 未持久化证明、request override 8 组无传输、models 无墙钟源码断言、ORM required 时间戳）
- package isolation PASS（fresh venv + FixedClock smoke）；Anti-AstrBot PASS

## AGENT_DISCOVERED_DELTA（M2a.2）

- [PROVIDER_FACT]：构造函数即校验（secret/numeric）→ 非法配置 fail-fast 于构造，无需等 HTTP
- [STORAGE_FACT]：models 无墙钟默认后，直接 ORM 建行必须显式传时间戳（repository 已全部显式）
- [TEST_FACT]：httpx MockTransport 的 extensions.timeout 是 per-phase dict
- [WORKFLOW_FACT]：HANDOFF/PROJECT_STATE 的"顶部正确但底部腐烂"模式已两次出现（M1.3/M2a.1）——已在 AGENT_MEMORY 固化预防
- [UNVERIFIED_HYPOTHESIS]：真实 Provider 端点的 json_schema/数值契约兼容性（M2b 确认）

## REAL ENV

- M1 REAL ENV VERIFIED 保留（2026-08-10）；M2a.2 无新 REAL ENV 声明

## 当前已知未知

- 真实 Provider（如 Ark）json_schema 支持度与 timeout 语义（M2b 真实验收）
- 无迁移框架；未来 schema 版本需人工迁移（M2a.1 决定）

## 下一步

- 外部 ChatGPT M2a 最终复核（12 项审核点见 REVIEW_REQUEST）→ PASS 后 M2b 授权

## 本轮修改文件

- 修改：providers/validation.py（+validate_provider_config_numeric/validate_request_override）、providers/openai_compatible.py（共享校验 + 构造校验 + chat 前置校验 + 删死函数）、repositories/repositories.py（数值校验）、storage/models.py（去墙钟默认）
- 新增：tests/unit/test_m2a2_fixes.py
- 修改：双 Memory（§9H）、.ai-handoff/ 6 文件
