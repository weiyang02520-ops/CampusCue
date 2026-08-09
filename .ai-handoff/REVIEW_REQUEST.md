# REVIEW_REQUEST.md

> M0.2 复核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核本轮修复。

## 请求审核内容

**4 项残留修复**（对照 M0.2 prompt finding 1-4）：

1. `docs/v2/07_RUNTIME_LIFECYCLE.md` —— 失败隔离改 OneBot Reverse WS server 语义（无 outbound 指数退避；SSE 等 client 模块例外说明）
2. `docs/v2/05_V2_ARCHITECTURE.md` —— 任务流改 progressive activation（L0-L7 M2 / L8 M3 / L9 M5），与 10/17/07 一致
3. `docs/context/CHATGPT_MEMORY.md` + `AGENT_MEMORY.md` —— 动态 HEAD 反模式修复（recovery 时从 Git 获取；里程碑 commit 保留 HISTORY）
4. `docs/v2/08_PROVIDER_AND_AGENT.md` —— M2 Provider Foundation 与 M4 Tool System 解耦（LLMRequest 无 ToolSet 依赖；tool_calls/tools 标 M4 EXTENSION）

**MEMORY DELTA 写入**：4 条（见 HANDOFF.md）是否正确写入双 Memory、provenance 是否正确。

## 需要确认的结论

1. 4 项修复语义是否准确（非表面替换）
2. Memory health：CURRENT TRUTH 无过时 HEAD；HISTORY 保留里程碑 commit；Current vs History 无冲突
3. 跨文档语义一致性：8 概念 × 8 文件（04/05/07/08/10/17/两个 Memory）
4. 无 V2 源码创建

## 风险与未验证项（诚实声明）

- M0.2 零代码、零测试运行
- 修复均为文档层；M1 仍 READY_NOT_STARTED

## Real Verified vs Not

- **CONFIRMED**：文件内容级修改（git diff 可查）
- **NOT VERIFIED**：无 REAL ENV（无代码）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
