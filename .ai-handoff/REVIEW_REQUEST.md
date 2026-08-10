# REVIEW_REQUEST.md

> M2b.1 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 Task Extraction Pipeline。

## 请求审核内容（对照 M2b.1 prompt §63 的 17 项）

1. **L0 source gating**：仅 group + enabled + auto_extract；未配置不自动创建
2. **无持久化 L1 闲聊历史**：L0/L1 拒绝 → 0 Extraction 行（隐私决策）
3. **ContextCollector bounded / 无当前消息重复**：snapshot 用 message_id 排除当前
4. **无跨 source 上下文污染**：per-source keyed buffer
5. **TaskExtractor 用 Provider 抽象**：业务代码不建 HTTP JSON；走 LLMRequest response_schema
6. **schema fallback 仅适当错误**：仅 INVALID_REQUEST 重试一次（测试断言恰 2 次调用）；AUTH/TIMEOUT 无 fallback
7. **parser 安全**：无 eval；宽容解析（plain/fenced/padded）失败即 ExtractionError
8. **事件时间戳锚定时间解析**：resolve_deadline(phrase, event.timestamp, tz)；持久化/去重另用 Clock
9. **UTC 持久化正确**：周五晚上12点+08 → 2026-08-14 15:59 UTC（集成测试）
10. **dedup source scope + 36h + dismissed**：source-scoped；36h cutoff；dismissed 仍重复；归一化标题
11. **并发语义去重安全**：TaskService asyncio.Lock 串行化重查+insert；并发测试恰 1 Task
12. **TaskService 唯一写入边界**：pipeline 不直接调 TaskRepository.create
13. **低置信/未决截止 → pending_confirm**：decide_pending_confirm 测试
14. **Extraction audit 完整 + 隐私安全**：l1/l3/l4/l5/outcome；raw 仅本地 DB
15. **Runtime opt-in 保留 M1**：CAMPUSCUE_TASK_PIPELINE=1 才启用；禁用时 hello→received:hello 无 DB/Provider
16. **无 Reminder/Agent/API/WebUI**
17. **无真实 secret/PII 提交**：全合成 fixture

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN；REAL QQ M2：NOT RUN（M2b.2 验收）
- [UNVERIFIED_HYPOTHESIS] 真实 Provider json_schema 支持度（M2b.2 确认）
- submission_method 无专属列（CURRENT M2 LIMITATION，存 audit + description）

## Real Verified vs Not

- **CONFIRMED**：256 tests 全绿、fresh venv 隔离（+tzdata）、Anti-AstrBot、并发去重 1 Task
- **NOT VERIFIED**：真实 Provider 调用、真实 QQ 任务抽取

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
