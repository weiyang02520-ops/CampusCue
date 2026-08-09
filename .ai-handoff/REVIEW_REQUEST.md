# REVIEW_REQUEST.md

> M1 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核本轮 M1 实现。

## 请求审核内容

**重点文件**：

- `v2/src/campuscue/`（全部 15 个模块）
- `v2/tests/`（unit 49 + integration 16）
- `v2/scripts/check_no_astrbot.py`
- `docs/v2/adr/ADR-011_V2_CODE_ISOLATION.md`

## 需要确认的结论（对照 M1 prompt §73 的 15 项）

1. **V2 是否真的与 Legacy/V1 隔离**：独立 `v2/` root；fresh venv 安装验证（证据：`/tmp/ccv2-fresh` site-packages import）
2. **是否存在任何 astrbot import / runtime dependency**：Anti-AstrBot Gate 报告 PASS（AST 扫描 + pyproject 依赖 + 隔离 smoke）
3. **CampusEvent 是否 OneBot-independent**：字段全部平台中立；OneBot raw JSON 只在 adapter 边界
4. **Reverse WS server ownership**：CampusCue 是 SERVER；NapCat 是 client；无 outbound reconnect
5. **stale connection replacement race**：generation 机制 + 单测覆盖（stale cleanup 不清新 active）
6. **Event vs Action Response frame 区分**：classify_frame 纯函数 + 单测 + 集成（action response 绝无 CampusEvent）
7. **echo correlation 是否 leak Future**：register-before-send；成功/超时/断连/替换全部 cleanup（pending 有界）
8. **disconnect 是否 fail pending**：立即 fail（不等 timeout）+ 集成测试
9. **queue / in-flight / pending actions 是否全部 bounded**：queue maxsize、semaphore max_in_flight、pending max + 超限拒绝
10. **transport dedup 只执行一次**：canonical point = adapter ingress；Router 无 stateful dedup；集成测重复消息单 action
11. **self-message 阻断 echo loop**：canonical suppression + Router stateless 防御；集成测 self 消息无回复
12. **normal logs 是否泄漏隐私**：NORMAL 模式不记录 ID/群号/正文；diagnostic 模式默认 OFF 且不进 Git
13. **fake integration 是否真的走完整链路**：真实 WS server + fake NapCat client，action/echo/响应全验证
14. **REAL ENV 是否真的执行**：**未执行**（本机无 NapCat）——诚实声明 IMPLEMENTED_AWAITING_REAL_ENV
15. **是否偷偷实现了 M2**：无（无 DB/无 Provider/无 Task/无 API/无 WebUI）

## 风险与未验证项（诚实声明）

- REAL ENV VERIFIED = NO（无 NapCat 环境）
- 真实 NapCat token handshake 行为未确认（按 OneBot 标准实现）
- NapCat `message.post-format` 是否默认 array 未确认（converter 拒绝 string 格式）
- 本机 Python 3.14.4 + websockets 16.0 环境已验证；其他环境未测

## Real Verified vs Not

- **CONFIRMED**：65 tests 全绿（unit+integration）、fresh venv 隔离安装、Anti-AstrBot Gate、git diff（Legacy 零改动）
- **NOT VERIFIED**：真实 QQ hello → received: hello

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
