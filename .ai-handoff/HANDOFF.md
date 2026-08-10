# HANDOFF.md

> 当前操作状态（canonical，单一文档）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY / Git history。

## 当前（M2b.1 Task Extraction Pipeline）

- **本轮**：实现 M2b.1（L0-L7 任务抽取管道 + Mock Provider + SQLite 全链路）
- **状态**：M2b PIPELINE_IMPLEMENTATION_COMPLETE — AWAITING_EXTERNAL_REVIEW
- **Gate**：M0/M1/M2a = PASS；**M2 = IN_PROGRESS（M2b.1 完成待复核；M2b.2 NOT_AUTHORIZED）；M2 FINAL = NOT PASS**

## 本轮完成

1. **tasks 包**：models（TaskCandidate/ExtractionResult/JSON Schema）、prompts、source_policy（L0：仅 group + enabled + auto_extract）、prefilter（L1：V1 行为移植，threshold 3.0）、context（L2：bounded per-source ring buffer，L1 拒绝仍观察）、extractor（L3：Provider 抽象 + json_schema → fallback 一次 + 宽容解析 + 规范化）、time_normalizer（L4：V1 行为 + 事件时间锚 + zoneinfo）、dedup（L5：source-scoped + 36h + dismissed 仍重复 + 归一化标题）、pipeline（L0-L7 编排 + audit）
2. **TaskService**（唯一创建/去重边界）：进程内 asyncio.Lock 串行化 dedup 重查 + insert；DB UNIQUE 最终防线
3. **Runtime 接线**：CAMPUSCUE_TASK_PIPELINE=1 启用；禁用时 M1 无 DB/Provider 照常；Router 顺序 TaskPipeline → EchoHandler（hello 仍回复）
4. **隐私**：L0/L1 拒绝无 Extraction 行；source_text_reference/raw_result 仅本地 DB 不落日志；submission_method 存 audit + Task.description（CURRENT M2 LIMITATION）
5. **平台依赖**：Windows 需 tzdata（zoneinfo）——已加 pyproject 平台标记依赖
6. **脚本**：scripts/m2_configure_source.py（conversation ID 走环境变量）

## 测试

- **256 passed**（新增 53：单元 43 + 集成 10）；全链路 Mock Provider → 真实 SQLite Task 行验证（周五晚上12点→2026-08-14 15:59 UTC）；并发同义务双管道 → 恰 1 Task；L0/L1 拒绝 0 provider 0 extraction；审计 l1/l3/l4/l5/outcome 完整
- package isolation PASS（fresh venv + tzdata + DB smoke）；Anti-AstrBot PASS

## AGENT_DISCOVERED_DELTA（M2b.1）

- [PIPELINE_FACT]：Windows Python 无 IANA tzdata → ZoneInfo('Asia/Shanghai') 抛 ZoneInfoNotFoundError；需 tzdata 平台依赖（已加）
- [CONTEXT_FACT]：snapshot 用 message_id 排除当前消息（LLM 输入中当前消息恰出现一次）
- [TEST_FACT]：pipeline 测试注入用 _FakeManager（manager 边界 fake，provider→transport→parse 仍真实）
- [PROVIDER_FACT]：json_schema INVALID_REQUEST → fallback 恰一次（有测试断言调用次数）
- [DESIGN_CONFLICT]：submission_method 无专属列 → 存 audit + description（记录为 CURRENT M2 LIMITATION，M2b.1 不做迁移）
- [UNVERIFIED_HYPOTHESIS]：真实 Provider（如 Ark）json_schema 支持度（M2b.2 确认）

## REAL ENV

- M1 REAL ENV VERIFIED 保留（2026-08-10）；M2b.1 **无真实 Provider/QQ 声明**（M2b.2 验收）

## 当前已知未知

- 真实 Provider json_schema/timeout 兼容性（M2b.2）
- 真实 NapCat 消息的 deadline_phrase 多样性（M2b.2 抽样确认）

## 下一步

- 外部 ChatGPT M2b.1 源码复核（17 项审核点见 REVIEW_REQUEST）→ PASS 后 M2b.2 授权

## 本轮修改文件

- 新增：v2/src/campuscue/tasks/{__init__,models,prompts,source_policy,prefilter,context,extractor,time_normalizer,dedup,pipeline}.py、services/task_service.py、tests/unit/test_m2b1_units.py、tests/integration/test_m2b1_pipeline.py、scripts/m2_configure_source.py
- 修改：config.py（TaskPipelineConfig）、app/runtime.py（可选启用 + DB dispose）、repositories（find_recent_for_source）、pyproject（+tzdata/tasks 包）、10_TASK_PIPELINE、README、双 Memory、.ai-handoff/
