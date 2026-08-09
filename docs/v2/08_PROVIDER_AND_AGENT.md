# 08_PROVIDER_AND_AGENT.md

> Provider / Tool / Agent Runtime 设计（M4 实现）。参考 AstrBot 思想（统一签名 + 注册表 + 请求实体承载工具链路），但只实现最小稳定版本。

## Provider

### 抽象（第一版只做一类）

```python
class BaseProvider(ABC):
    provider_type: str          # "openai_compatible"
    async def chat(self, request: LLMRequest) -> LLMResponse
    # 第一版不做 text_chat_stream（流式）——YAGNI；需要时 M6+ 加
    async def test(self) -> ProviderTestResult   # 最小 chat 连通性测试
```

- **LLMRequest**：messages（system + user + tool results）、model、temperature、max_tokens、timeout、tool_schema（ToolSet 转换后）、`disable_thinking`（能力位，V1 直连 Ark 的原因在此表达，不绕过 Provider 层）
- **LLMResponse**：role、content、tool_calls（name/args/id）、usage、raw（不落日志）
- **ProviderManager**：注册表（name → provider 工厂）+ 配置驱动实例化 + `get_default()` / `get_by_id()` + 测试连接；**不实现**热更新/多 provider 偏好/fallback 链（第一版一个默认 provider 足够）

### OpenAICompatibleProvider

- 用 httpx 直连 `{base_url}/chat/completions`（不做 SDK 依赖）
- 支持：tools schema 传入、tool_choice、json_schema 约束（structured output，供提取管道复用）
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

## Tool

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

## Agent Runtime（最小 Tool Loop）

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
