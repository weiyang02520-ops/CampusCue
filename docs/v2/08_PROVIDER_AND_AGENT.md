# 08_PROVIDER_AND_AGENT.md

> Provider / Tool / Agent Runtime 设计。参考 AstrBot 思想（统一签名 + 注册表 + 请求实体承载工具链路），但只实现最小稳定版本。
> **Milestone 边界（I 修正）：Provider Foundation 在 M2 完成（Task Extraction 使用它）；M4 只在已有基础上增加 Tool 系统与 AgentRuntime，不重新造 Provider。**

## Milestone 分配

| 组件 | 激活于 |
|---|---|
| BaseProvider / LLMRequest / LLMResponse / ProviderError taxonomy / OpenAICompatibleProvider / 最小 ProviderManager / structured output / secret_reference | **M2**（Task Extraction 的 LLM 调用走它） |
| ToolDefinition / ToolResult / ToolRegistry / Task Tools / CampusAgentRuntime / ContextBudget / Tool Loop / conversation 最小实现 | **M4（已实现；Real Provider Tool Call 与 safe independent-test-bot QQ E2E 尚待运行）** |
| 流式 / fallback provider 链 / 多 provider 偏好 | FUTURE |

## Provider（M2 激活）

### 抽象（第一版只做一类）

```python
class BaseProvider(ABC):
    provider_type: str          # "openai_compatible"
    async def chat(self, request: LLMRequest) -> LLMResponse
    # 第一版不做 text_chat_stream（流式）——YAGNI；需要时 M6+ 加
    async def test(self) -> ProviderTestResult   # 最小 chat 连通性测试
```

- **LLMRequest（M2 最小集合，不依赖 Tool System）**：messages（system + user）、model、temperature、max_tokens、timeout、structured output / response schema（json_schema 约束）、`disable_thinking`（能力位，V1 直连 Ark 的原因在此表达，不绕过 Provider 层）。**M2 Provider Foundation 独立于 Tool System 存在**（无 ToolSet/ToolRegistry/ToolDefinition/AgentRuntime 依赖）。
- **LLMResponse（M2 最小集合）**：role、content、usage、raw（不落日志）。`tool_calls` 字段：**M4 EXTENSION / inactive until M4**——provider-neutral optional capability（openai 协议天然会回传，解析为可选字段即可），不要求 M2 实现任何 Tool 系统；M4 再正式启用。
- **ProviderManager**：注册表（name → provider 工厂）+ 配置驱动实例化 + `get_default()` / `get_by_id()` + 测试连接；**不实现**热更新/多 provider 偏好/fallback 链（第一版一个默认 provider 足够）

### OpenAICompatibleProvider

- 用 httpx 直连 `{base_url}/chat/completions`（不做 SDK 依赖）
- M2 支持：json_schema / response_format 约束（structured output，供 Task Extraction 使用）、timeout、disable_thinking（若端点支持）
- **tools / tool_choice 传入：M4 EXTENSION**（M2 不实现、不使用；协议层字段存在即可，不接线）
- 错误分类（V1 教训：不能 except Exception → "AI 请求失败"）：

| 分类 | 特征 | UI 文案 |
|---|---|---|
| timeout | 超时 | 请求超时，请检查网络或模型响应速度 |
| auth_error | 401/403 | API Key 无效或无权限 |
| rate_limit | 429 | 请求过于频繁，稍后重试 |
| invalid_model | 400 模型不存在/参数错 | 模型配置无效，请检查模型名 |
| context_overflow | 请求超 max_context_tokens | 内容过长，请简化问题 |
| network | 连接失败 | 无法连接模型服务，请检查 Base URL |
| malformed_output | 结构化输出解析失败 | 模型返回格式异常（重试一次后报错） |

## Tool（M4 激活）

```python
class ToolDefinition:
    name: str
    description: str
    input_schema: dict        # JSON Schema（参数校验用 jsonschema）
    permission: str           # 第一版统一 "task"
    async def execute(self, **kwargs) -> ToolResult

class ToolResult:
    ok: bool
    content: str              # 给 LLM 的文本
    data: dict | None
    error: str | None

class ToolRegistry:
    register / unregister / get / list / execute
```

第一版工具（语义 REUSE_BEHAVIOR from V1 tools.py，接口重写）：

| name | 说明 |
|---|---|
| task_list | 查待办（scope: open/today/week/overdue/done/pending；返回含"还剩N天"） |
| task_get | 单任务详情（含来源引用） |
| task_create | 口述建任务（走 TaskService，dedup 生效） |
| task_update | 改标题/课程/截止（截止变化触发提醒重建） |
| task_complete | 完成（取消提醒） |
| task_dismiss | 忽略（取消提醒） |
| reminder_list | 查提醒 |
| source_list | 查来源（可选，M4 按需） |

- 执行前：jsonschema 校验参数；失败返回 ToolResult(ok=False, error=校验错误)
- 执行中：超时（如 30s）；异常 → error 回填（不让 LLM 看到堆栈）
- 作用域：默认按来源会话（V1：工具只能看/改本群任务——保留该边界）
- **M4 第一版创建限制**：M2 的唯一约束 `(source_id, source_message_id)` 使同一 Agent 用户消息最多创建一个 Task。第二次 `task_create` 返回安全失败结果，由 Agent 如实告知用户；M4.1 不引入 schema v3。

## Agent Runtime（M4 激活，最小 Tool Loop）

```
User Input
  → AgentContext（conversation + ContextBudget）
  → Provider.chat（含 tools schema）
  → 无 tool_calls → Final Response
  → 有 tool_calls → 逐条:
        validate args → ToolRegistry.execute → ToolResult
  → append（tool result 以消息形式进上下文）
  → 再 Provider.chat
  → ... 直到无 tool_calls 或达上限
```

- **max_steps：默认 6，上限 8**（V1/AstrBot 默认 30 对校园问答过重）
- **防呆**：
  - 无限循环：step 上限
  - 重复完全相同 tool call：连续 ≥3 次相同 → 强制中止并提示模型（V1 的 streak 检测保留）
  - Tool 超时 / Tool 错误 / Provider 错误：捕获分类，向用户展示可理解的文案
  - Context Overflow：ContextBudget 触发裁剪/摘要 → 停止
  - 用户中断：abort 信号与 LLM 调用赛跑（参考 AstrBot `_await_or_stop` 思想，实现从简）
- **上下文预算（ContextBudget）**：system + conversation + tool results + input + reserve output ≤ max_context_tokens。第一版不做长期记忆：超预算时丢弃最旧消息/摘要工具结果

## Conversation（第一版）

- 按来源会话维度：`group:{group_id}` / `private:{user_id}` 一个 thread
- 仅保留最近 N 轮（如 20 条）+ 工具结果保留一页（即上一轮）
- 不做跨会话聚合（YAGNI）

## 不实现（第一版，写入 NEXT_TASKS）

SubAgent / Handoff / MCP / Skills / Computer Use / 流式（可 M6 后补）
