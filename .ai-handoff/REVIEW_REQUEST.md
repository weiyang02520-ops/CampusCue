# REVIEW_REQUEST.md

> M1.2 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 M1 REAL ENV 验收。

## 请求审核内容（finding A-H 修复对照）

1. **A stale finally 竞态**：adapter.py pending map 按连接替换；新回归测试走真实 `_handle_connection` 生命周期（不再手工模拟 half-finally）
2. **B outbound 绕过并发限制**：runtime._route_event 内直接 `await adapter.send` + ActionFailure 捕获；测试验证慢 send 时活跃管道 ≤ max_in_flight
3. **C pending backpressure**：Semaphore 等待而非报错；取消不泄漏 slot（finally release）；测试 max=1 B 等待 A
4. **D config fail-fast**：RuntimeConfig.__post_init__ 拒绝 0/负值/非法 port/path；7 项拒绝测试
5. **E WS path contract**：process_request 校验 path（404）；集成测试错误 path 拒绝
6. **F 严格响应校验**：`status=="ok" AND retcode==0`；缺字段 = failed；7 项测试
7. **G diagnostic 假 claim**：__main__ 修正为 verbose debug 不 dump 明文；17_MILESTONES 同步
8. **H raw_message 移除**：CampusEvent 无 OneBot 方言字段；测试验证

## 需要确认的结论

- 修复语义是否正确（非表面替换）
- 回归测试是否真的覆盖真实路径（尤其 finding A 的 stale finally）
- 旧测试语义变更是否合理（test_actions.py::test_max_pending_bound → backpressure 语义）
- 是否偷偷实现了 M2（无）

## 风险与未验证项（诚实声明）

- REAL ENV VERIFIED = NO（本机无 NapCat）
- 真实 NapCat token/path handshake 行为未确认
- M1.1 为 source correctness fix；真实联调留 M1.2 / Real Env Gate

## Real Verified vs Not

- **CONFIRMED**：87 tests 全绿（unit 70 + integration 17）、fresh venv 隔离、Anti-AstrBot Gate、git diff（Legacy 零改动）
- **NOT VERIFIED**：真实 QQ hello → received: hello

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
