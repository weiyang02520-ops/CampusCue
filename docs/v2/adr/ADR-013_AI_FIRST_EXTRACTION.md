# ADR-013：AI-First Task Extraction

- **Status**：Accepted（M2b.1）
- **Date**：2026-08-10
- **Context**：校园群消息高度自然、不完整、依赖上下文（"这个周五前交一下"、"还是按之前那个时间"）。关键词/正则 gating 会产生不可接受的假阴性。用户产品决策：第一版优先减少漏掉真实校园事务，而不是极限节省 LLM Token。
- **Decision**：**CampusCue M2 使用 AI-first 语义理解**。本地确定性代码不做主要任务分类。本地阶段职责限于：
  1. **MessageHygieneFilter**：仅对高确定性无效内容 hard drop（empty/空白/超长/无文本）；禁止"关键词不足/不像任务"类主观 reason。
  2. **LocalSignalAnalyzer**：纯函数 hints（deadline/time/action/affair/authority/coursework），score 是 metadata，**绝不作为调用 LLM 的门槛**（score=0 的正常消息仍进 LLM）。
  3. 确定性校验（枚举/title/confidence）、时间解析、去重、安全兜底。
- **LLM 单次调用**：一次完成 task triage + structured extraction（输出 has_task/category/title/course/deadline_phrase/submission_method/confidence/reason）。正常路径 1 call；schema INVALID_REQUEST → fallback 恰一次（总上限 2 calls）。禁止先分类再抽取两次调用。
- **Alternatives**：旧 LocalPrefilter score-threshold gate（拒绝：SUPERSEDED——假阴性不可接受）；小模型二级 triage（拒绝：YAGNI，真实成本数据出来后再优化）。
- **Reason**：产品优先级 Recall > 极致省 token；大模型核心价值正是理解不完整、上下文相关的自然表达。
- **Consequences**：更多 Provider 调用；更强的隐私纪律（model_said_none 审计不保存完整输入 context；只有创建 Task 才持久化 source_text_reference）；本地 signals 仍用于 audit/hints/未来统计；未来成本优化必须 evidence-driven。
