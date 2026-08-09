# 10_TASK_PIPELINE.md

> Campus Task Pipeline（M2 实现）详细设计。核心目标：减少无意义 LLM 请求、提高正确率、减少重复任务、保留可追溯来源。

## 分层设计

```
CampusEvent
  → L0 SourcePolicy    来源是否启用（group 白名单 + auto_extract）
  → L1 LocalPrefilter  本地规则预筛（省 token，纯代码）
  → L2 ContextCollector 最小上下文（当前消息 + 必要最近上下文，不拉群历史）
  → L3 LLM Extract     结构化 Schema 输出（必须 JSON Schema 约束）
  → L4 TimeNormalizer  时间标准化（显式 timezone / current_time 注入）
  → L5 Deduplicator    去重（指纹组合 + explainable reason）
  → L6 Confidence      低置信度 → 待确认状态
  → L7 TaskService.create（统一创建入口，唯一写路径）
  → L8 ReminderService 建立提醒
  → L9 Realtime        通知 Web
```

## L0 SourcePolicy

- 输入：CampusEvent（conversation_id + conversation_type）
- 规则：来源存在且 `enabled=true` 且 `auto_extract=true`；未配置来源 → 直接丢弃（不创建任务）
- 输出：pass / drop(reason)

## L1 LocalPrefilter（REUSE_BEHAVIOR from V1 prefilter.py）

- 纯规则关键词加权打分（V1：deadline 3.0 / time 3.0 / action 2.0 / affair 1.5 / authority 2.5，阈值 3.0）
- 中文时间正则（周五/今晚/月底…）、课业引用正则（页/习题/章节）
- `PURE_CHATTER` 全消息剔除闲聊；长度 4-2000
- 关键要求：**零 LLM 调用、零 astrbot 依赖、可单测**（V1 已验证：0 个 astrbot import）

## L2 ContextCollector

- 只取：当前消息 + 来源的最近 N 条上下文（N=context_window，默认小，如 5）
- 上下文仅用于消歧（"这个"指什么、课程名补全），**不把群历史全文送 LLM**（隐私，见 14_SECURITY_PRIVACY）

## L3 LLM Extract（REUSE_BEHAVIOR from V1 llm.py，但升级）

- 输入：candidate message + minimal context
- **必须使用 JSON Schema 约束结构化输出**（V1 用 `json_object` + 宽容解析，V2 优先 API 级 `response_format: json_schema` 或等价约束；不支持时降级 + 宽容解析）
- 输出 Schema（草案）：
```json
{
  "has_task": true,
  "category": "homework|exam|competition|activity|notice|other",
  "title": "第三章作业",
  "course": "高等数学",
  "deadline_phrase": "周五晚上12点前",
  "submission_method": "学习通",
  "confidence": 0.9,
  "reason": "含截止时间与提交方式"
}
```
- 解析失败策略：重试一次（若合理）→ 仍失败记 extraction error → 不创建任务
- 未知字段：忽略并记录；缺 deadline：允许（进入待确认，非失败）
- Provider 通过 ProviderManager 调用（V1 直连 Ark 的原因——thinking:disabled + 无会话历史污染——应在 BaseProvider 配置能力中表达，如 `disable_thinking` 能力位，而不是绕过 Provider 层）

## L4 TimeNormalizer（REUSE_BEHAVIOR from V1 timeresolve.py + 修复）

- `resolve_deadline(phrase, current_time, timezone)`——**current_time 与 timezone 必须可注入**（V1 缺口：CAMPUS_TZ 模块常量不可注入；V2 修复，测试用固定时钟 + 固定时区）
- 保留 V1 已验证约定：晚上+12点→23:59、今晚→23:59、明早→8:00、裸日期→23:59(is_explicit=False)、跨年 +1 年、星期间距周日锚定、拒绝"上/上上"、过去 2h 容忍、未来 400 天上限、解析失败进待确认
- 系统时区：显式配置（默认 Asia/Shanghai），per-user profile.timezone 支持（V1 定义了字段但未打通）

## L5 Deduplicator（REWRITE from V1 store.dedup_key）

- V1：sha256(umo|归一化标题|deadline到分钟) + 36h 窗口 → 保留，但补强
- V2 组合指纹（按序取存在者）：
  1. source_message_id（同一消息只处理一次，最硬）
  2. 归一化标题 + course + deadline(到分钟)（V1 核心）
  3. 归一化标题 + deadline(到分钟)（无 course 时）
  4. 内容相似（title 编辑距离 ≤ 阈值 且 deadline 相同，仅对低置信度）
- 时间窗口：36h（与 V1 一致）
- **dismissed 任务仍算重复**（防重新抽取，V1 已验证行为）
- 要求：`explainable reason`——命中重复时记录命中的 key 与候选，供消息页显示"为何未创建"

## L6 Confidence

- confidence < 阈值（默认 0.6，profile 可调）→ 任务进入 `pending_confirm` 待确认状态
- 待确认任务：WebUI 消息页明示，用户可确认/拒绝；确认后进正常任务流
- 不因低置信度丢弃（保留 evidence：source_text_reference + reason）

## L7 TaskService.create（唯一创建入口）

- 签名：`create_from_extraction(extraction, dedup_result, source) -> Task | DuplicateError`
- 职责：校验 → 查重 → 落库 → 触发 ReminderService → 发 Realtime 通知
- **禁止**：API 直接建任务、Agent Tool 直接建任务（都必须走 TaskService）
- 重复返回 DuplicateError（409），附带 explainable reason

## L8 ReminderService

- `plan_reminders(task)`：三档排期（提前 1 天 / 2 小时 / 截止时刻）→ 见 10_REMINDER.md
- 幂等：先 cancel 再排；task 状态变化联动

## L9 Realtime

- 事件 `extraction.updated` / `task.created` → SSE（仅通知，见 11_API_SPEC Realtime 规则）

## 失败与审计

- 每层结果写入 `extractions` 表（L1 分数 / L3 原始与解析 / L4 决议 / 最终 outcome）
- LLM 原始输出只存本机溯源库，日志脱敏（V1 已验证）
- 管道任一层失败：记 extraction error + 不创建任务 + 不静默（消息页可见）
