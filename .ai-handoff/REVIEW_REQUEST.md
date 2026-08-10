# REVIEW_REQUEST.md

> M2a 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 Data & Provider Foundation。

## 请求审核内容（对照 M2a prompt §54 的 15 项）

1. **schema/domain 一致性**：sources/tasks/extractions/provider_configs/schema_meta 与 ADR-012 一致
2. **TaskStatus 矛盾已解决**：唯一枚举 pending_confirm/pending/done/dismissed（storage/enums.py）
3. **Extraction audit 足够 M2b**：audit JSON 结构（l1/l3/l4/l5/outcome）+ raw_result 本地 DB 不落日志
4. **Source 身份唯一性**：(platform, conversation_id) 复合唯一约束（跨平台允许复用 ID）
5. **SQLite 时区正确**：UTCDateTime TypeDecorator（写 UTC/读 aware；naive 拒绝；+08:00→UTC 测试）
6. **DB 测试隔离**：CAMPUSCUE_ENV=test 无显式路径即 FAIL；测试全用 tmp_path
7. **事务边界**：每个 repository 方法独立短事务；IntegrityError → rollback → DuplicateError
8. **无真实 DB/PII 进 Git**：测试 DB 全临时；生产 DB 路径 data/ 已 gitignore
9. **secret_reference 不存 secret 值**：测试证明 DB 只有引用名；格式正则校验
10. **Provider 错误分类**：9 类 taxonomy（timeout/auth/rate_limit/network/invalid_model/context_overflow/malformed_output/invalid_request/server_error）+ 每类测试
11. **structured output wire 格式**：contract 测试断言 response_format.json_schema 到达请求体
12. **ProviderManager 默认歧义**：0→NoProviderConfiguredError；>1→AmbiguousDefaultProviderError；不静默选第一行
13. **Provider mocks 走真实解析**：httpx.MockTransport 注入真实 client，响应解析走生产代码
14. **无 Agent/Tool/M2b 实现**：无 Prefilter/Extractor/TimeNormalizer/Deduplicator/TaskService 占位
15. **M1 仍绿/独立**：139 tests（含 87 旧）；M1 runtime 启动不依赖 DB/Provider

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN（无可用真实 Provider 凭据；M2b 真实验收）
- REAL QQ：M1.2 prior verification 保留；**无新 M2 REAL ENV 声明**
- [UNVERIFIED_HYPOTHESIS] 真实端点（如 Ark）json_schema 支持度——M2b 确认
- M2a 无 Task Pipeline（M2b 范围）

## Real Verified vs Not

- **CONFIRMED**：139 tests 全绿（unit+integration+contract）、fresh venv 隔离安装含 DB smoke、Anti-AstrBot Gate、secret 值不进 DB（测试）
- **NOT VERIFIED**：真实 Provider 调用、真实 QQ 任务抽取

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
