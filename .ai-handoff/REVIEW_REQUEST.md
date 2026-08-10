# REVIEW_REQUEST.md

> M2b.1（AI-first）审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 AI-First Task Extraction Pipeline。

## 请求审核内容（对照 AI-first prompt §75 的 18 项）

1. **本地规则不再语义 gate**：prefilter.py 拆为 HygieneFilter（hard drop 仅 empty/空白/超长/无文本）+ SignalAnalyzer（hints）
2. **正常低分消息仍达 Provider**：测试"这个周五前交一下" provider call == 1；模糊消息 4 条强制回归
3. **明显垃圾可 hard drop**：空/空白/纯表情 → 0 provider 0 extraction 0 task
4. **ContextCollector 帮助模糊消息**："高数第三章"+"这个周五前交学习通"→ 提取完整作业
5. **当前消息不重复**：snapshot 排除 message_id（断言恰一次）
6. **无持久化聊天历史**：model_said_none 审计无完整输入 context；仅 Task 存 source_text_reference
7. **LLM 单次 triage+extraction**：正常路径 1 call（测试断言）
8. **fallback 有界 ≤2 calls**：schema INVALID_REQUEST → 恰一次 fallback（断言 2 calls）
9. **parser 安全**：无 eval；宽容解析失败即 ExtractionError
10. **事件时间戳锚定截止解析**：resolve_deadline(phrase, event.timestamp, tz)
11. **source-scoped 36h dedup**：同 source+语义+36h；跨 source 不重复
12. **并发去重安全**：TaskService lock 串行化；并发测试恰 1 Task
13. **TaskService 唯一业务写入路径**：pipeline 不直接 Repository.create
14. **低置信 → pending_confirm 不丢弃**：decide_pending_confirm 测试
15. **model_said_none 审计隐私**：skipped Extraction 无输入文本
16. **M1 Echo 不受影响**：pipeline disabled → hello → received: hello
17. **无 Reminder/Agent/API/WebUI**
18. **无真实 key/PII**：全合成 fixture

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN；REAL QQ M2：NOT RUN（M2b.2 验收）
- [UNVERIFIED_HYPOTHESIS] 真实 Provider json_schema 支持度与真实 token 成本（M2b.2 确认；成本可观测性留未来）
- submission_method 无专属列（CURRENT M2 LIMITATION）

## Real Verified vs Not

- **CONFIRMED**：264 tests 全绿、fresh venv 隔离（+tzdata）、Anti-AstrBot、并发去重 1 Task、AI-first 低分进 Provider
- **NOT VERIFIED**：真实 Provider 调用、真实 QQ 任务抽取

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
