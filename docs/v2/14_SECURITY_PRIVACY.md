# 14_SECURITY_PRIVACY.md

> 安全与隐私设计约束。CampusCue 处理真实私人聊天内容 → **Privacy by Architecture**，默认 local-first。

## 秘密管理

- 正式配置只保存 `secret_reference`（如 `CAMPUSCUE_ARK_API_KEY` 环境变量名）
- 真实 API Key / QQ token / 凭据：环境变量或 OS Credential Store；`.env` 永远 gitignore
- 日志永远不打印 secret（含调试级）
- Provider API 响应/错误中的 key 片段脱敏

## QQ 隐私（消息处理）

- **不把整个群历史送 LLM**：L1 本地预筛 → 候选消息 → L2 最小上下文（默认 5 条）→ LLM
- 默认不保存完整群聊全文；只保存被识别任务的来源消息（source_text_reference）
- 消息保留策略可配置（保留时长），到期清理
- 日志默认不记录：消息正文、发送者、群号、任务标题、截止时间、推送目标（V1 已验证并有回归测试，V2 保持）

## 日志脱敏（B11 教训）

- 日志内容：timestamp / level / trace_id / event_id / component / action / duration / status
- 敏感内容：不记录原文，用 message_id / length / hash / category / trace
- LLM 原始输出只落本机溯源库（extractions 表），不进日志
- 错误日志分类：预期断线（WARN 限频）/ 用户配置错误 / Provider 错误 / Internal Bug（ERROR 带 trace_id）
- 相同错误聚合限频（禁止 WS 一断每毫秒 ERROR 刷几 GB 日志）

## 网络暴露面

- 默认仅监听 `127.0.0.1`（WebUI/API/OneBot WS 入口）
- 允许 LAN：必须重新设计安全模型（token/密码认证 + HTTPS 或代理），M5 定稿
- OneBot WS server：仅接受本机 NapCat（127.0.0.1 或校验 token 头），防外部伪造消息注入

## API 安全（M5 已实现）

- 默认 loopback 无认证（本地使用）；`CAMPUSCUE_REQUIRE_AUTH=1` 或非 loopback host 启用认证；token 只来自 `CAMPUSCUE_API_TOKEN`，不落 DB/日志/Git
- 所有用户输入（API / Tool / OneBot）校验：Pydantic / jsonschema / 枚举闭集
- 破坏性操作（恢复、删除）：显式确认字段（V1 `confirm_replace` 模式保留）
- SSE 慢 subscriber 使用 bounded queue，溢出断开而非阻塞业务

## 测试隔离（硬性）

- `CAMPUSCUE_ENV=test`：runtime 启动断言数据目录/数据库/端口为测试专用（`tmp` 路径）
- 测试 / demo / E2E 永不连接生产数据目录（B07 教训）
- destructive 测试（删除/恢复）执行前必须证明隔离

## 仓库边界

禁止进入 Git：`.env*`、`*.key`、`*.pem`、`credentials*`、`secrets*`、真实数据库备份、QQ/NapCat 认证数据、运行日志含敏感内容。checkpoint secret scan 强制（见 `.ai-handoff/STATUS.md` 流程）。
