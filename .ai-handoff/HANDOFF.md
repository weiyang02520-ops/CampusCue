# HANDOFF.md

> M1.1 Runtime Correctness Fix 交接记录。由工作区 AI 在 checkpoint 前更新。
> 上一轮：M1（9bfb018）。本轮：外部源码审核 8 项 correctness 修复。

## 本轮目标

修复 External ChatGPT 对 M1 源码独立审核发现的 8 项 correctness / boundedness / protocol contract 问题（finding A-H）。**未实现任何 M2 内容（无 DB/Provider/Task/Reminder/Agent/API/WebUI）。**

## 本轮完成（finding 修复对照）

| # | Finding | 修复 |
|---|---|---|
| A | stale connection finally 无条件 `_fail_all_pending`，可能清掉新连接的 pending | pending map 按连接替换：新连接接管时换新 map 并显式 fail 旧 map；finally 仅在仍持有 active slot 时 fail；**回归测试走真实 `_handle_connection` 生命周期** |
| B | `_route_event` create_task 绕过 EventBus 并发限制 | outbound send 移入 handler 内 `await`（完整链路 bounded）；ActionFailure 捕获记脱敏日志；删除无用 `_outbound_task`；**测试：慢 send 时活跃管道 ≤ max_in_flight** |
| C | pending 超限立即报错，非 backpressure | `asyncio.Semaphore(max_pending_actions)`：达到上限 `await` 等待；finally 释放 slot（取消不泄漏）；**测试：max=1 时 B 等待 A 完成后继续** |
| D | 配置允许 0/负值（`Queue(maxsize=0)`=unbounded） | `RuntimeConfig.__post_init__` fail-fast：queue_maxsize/max_in_flight/max_pending/dedup_capacity/dedup_ttl/action_timeout 全部 >0；port 1-65535；path 以 `/` 开头；**7 项拒绝测试** |
| E | `cfg.path` 未强制 | `process_request` 校验 `request.path == cfg.path`（404 拒绝）；**集成测试：错误 path 拒绝、正确 path 成功** |
| F | 响应校验过宽松（缺字段也算成功） | `is_success` 严格：`status=="ok" AND retcode==0`；缺任一字段 = malformed/failed；**7 项严格测试** |
| G | `__main__` 声称 diagnostic 会打印 conversation/group/sender/message（假功能） | 修正为"verbose debug diagnostics"，**不 dump 明文 ID/消息/token**；真实 QQ 收到 expected response 即 E2E 证据；17_MILESTONES 验收表述同步 |
| H | `metadata={"raw_message": ...}` OneBot 方言泄漏进 Domain | 移除；CampusEvent 保持 platform-neutral；**测试：converter 输出无 raw_message** |

## 测试

- **87 passed**（旧 65 + 新增 22：test_m11_regressions 4 + test_m11_fixes 18）
- 修改 2 个旧测试语义并说明原因：
  - `test_actions.py::test_max_pending_bound`（旧断言"limit 错误"）→ `test_stale_pending_entry_does_not_block_new_send`（语义被 finding C 取代：backpressure 测试移到 test_m11_regressions）
  - `test_connection_generation.py` 保留但 M1.1 新增真实路径回归（finding A 教训：旧测试手工模拟 half-finally，未覆盖真实 finally）
- **PACKAGE ISOLATION PASS**（fresh venv 重装验证）
- **Anti-AstrBot Gate PASS**

## REAL ENV

- **NOT VERIFIED**：本机无 NapCat。M1.1 是 source correctness fix；真实联调留 M1.2 / Real Env Gate（外部审核复核后再做）。

## 实际修改文件

- 修改：v2/src/campuscue/adapters/onebot/adapter.py（A/C/E）、app/runtime.py（B）、config.py（D）、adapters/onebot/protocol.py（F）、__main__.py（G）、adapters/onebot/converter.py（H）
- 新增：v2/tests/unit/test_m11_regressions.py（4）、v2/tests/unit/test_m11_fixes.py（18）
- 修改：v2/tests/unit/test_actions.py（1 个测试语义更新）
- 修改：docs/context/CHATGPT_MEMORY.md（§9C 8 条 MEMORY DELTA）、AGENT_MEMORY.md（§7 新增 2 条失败模式 + rules 14-18）
- 修改：.ai-handoff/ 全套（STATUS/PROJECT_STATE/HANDOFF/REVIEW_REQUEST/CHANGELOG_AI/NEXT_TASKS）

## 真实测试

- 87 tests 全绿；fresh venv 隔离安装；Anti-AstrBot Gate；git diff 确认 Legacy 零改动
- REAL ENV：未执行（无 NapCat）

## Mock Tests / 未验证

- 真实 QQ hello 链路未验证；真实 NapCat token handshake 未确认

## AGENT_DISCOVERED_DELTA

- [REPO_FACT]：websockets 16 的 `process_request` 可同时用于 path + token 校验（handshake 阶段），实现已合并为 `_check_handshake`。
- [RUNTIME_FACT]：`asyncio.Queue(maxsize=0)` 在 Python 3.14 确实代表 unbounded——config fail-fast 是必要防护。
- [RUNTIME_FACT]：测试中 `__aiter__` 必须是非 async 方法（async 版本返回 coroutine 导致 `async for` 崩溃）——已修正测试辅助。
- [UNVERIFIED_HYPOTHESIS]：NapCat 默认 `post-format` array（converter 拒绝 string 格式）；真实环境确认。

## Known Bugs

- 无已知新 Bug。V1 遗留 B12/B13 待 M2 修。

## Architecture Changes / Decisions

- M1.1 修复 8 项（见上表）；MEMORY DELTA 8 条入双 Memory（§9C）；无新 ADR（实现细节级修复）

## Branch / Remote / Base

- 仓库：weiyang02520-ops/CampusCue（public）
- 本次提交：fix: harden M1 runtime lifecycle and backpressure
- Base：9bfb018（M1 commit）

## External Review Focus

- 见 REVIEW_REQUEST.md（finding A-H 修复对照 + 回归测试证据）
