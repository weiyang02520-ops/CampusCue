# REVIEW_REQUEST.md

> M2a.1 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 Foundation Correctness Fix。

## 请求审核内容（对照 M2a.1 prompt §25 的 12 项）

1. **provider.test 真实路径**：test_m2a1_fixes.py 走真实链（get_default → test → chat → MockTransport → parse）；test_default 经 get_default
2. **请求 timeout 到达传输**：LLMRequest.timeout_s=None 默认；request override > provider 默认；contract 测试断言 httpx extensions.timeout
3. **非法枚举值拒绝**：repository _require_enum（status/category/priority/extraction）+ 直接 SQL 插 banana 触发 CHECK 约束
4. **不兼容 DB 零变更拒绝**：预检（sqlite3 ro）先于任何写入；未来版本拒绝后 tasks/sources 不出现、version 行不变
5. **未知 DB 无 schema_meta 安全处理**：有用户表 → SchemaRefusedError 拒绝认领；无用户表 → fresh bootstrap
6. **Clock 实际控制持久化时间戳**：FixedClock 注入 → created_at/updated_at 确定；advance 确定性；naive clock 拒绝
7. **非法 secret_reference 无法进 DB**：providers/validation.py 共享规则；repository 持久化前拒绝（6 种非法样例测试）
8. **ProviderManager.get_by_id**：新增 + NotFound 测试
9. **畸形成功载荷拒绝**：缺 choices/空 choices/缺 message/缺 content/content null/类型错 → MALFORMED_OUTPUT
10. **非 JSON HTTP 错误按状态分类**：401 text/403 HTML/429 text/500 HTML 不读 body 正确分类；400 text→INVALID_REQUEST；200 text→MALFORMED
11. **无 M2b 实现**：无 prefilter/extractor/timeresolve/deduplicator/TaskService
12. **M1 回归保持绿**：186 tests（含 M1 87 旧）

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN（M2b 真实验收）
- REAL QQ：M1.2 prior verification 保留；无新声明
- 无迁移框架（M2a.1 明确不做）；未来版本 DB 需人工迁移

## Real Verified vs Not

- **CONFIRMED**：186 tests 全绿、fresh venv 隔离、Anti-AstrBot、schema 零变更（测试证明）
- **NOT VERIFIED**：真实 Provider 调用

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
