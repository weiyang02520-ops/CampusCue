# 16_MIGRATION_MAP.md

> 旧业务能力迁移决策总表（V1 → V2）。决策依据：[02_V1_AUDIT](02_V1_AUDIT.md) 详细审计。

## 迁移决策

| 旧能力 | V2 归属 | 决策 | 说明 |
|---|---|---|---|
| L1 规则预筛 | tasks/extraction/prefilter | **REUSE_BEHAVIOR** | 纯逻辑零耦合，直接迁移；V2 保持可单测 |
| L3 时间解析 | tasks/extraction/time_parser | **REUSE_BEHAVIOR** | 保留全部 V1 已验证约定；**修复时区注入缺口**（B12） |
| LLM 结构化抽取 | tasks/extraction/extractor | **REUSE_BEHAVIOR + REWRITE_INTEGRATION** | 保留 json_object + 宽容解析防御与 extraction 行为思想；**M2 起改走 V2 Provider abstraction**（不再业务层裸写厂商 HTTP，`disable_thinking` 以 Provider 能力位表达） |
| 提示词制品 | tasks/extraction/prompts | **REUSE_BEHAVIOR** | 调优产物，保留 |
| 去重（dedup_key + 36h 窗口） | tasks/dedup | **REUSE_BEHAVIOR**（补强） | 保留核心；补 source_message_id 指纹 + explainable reason |
| 5 张 campus_ 表 schema | storage/models | **REUSE_BEHAVIOR** | 表结构/枚举/UTC 约定照搬；换自有 engine |
| 数据访问层（db_helper 直连） | storage/repositories + services | **REWRITE** | 行为照搬，实现重写（自有 session，Service 唯一入口） |
| 5 个 FunctionTool 语义 | tools/ | **REWRITE** | 工具语义（list/create/complete/set_reminder/analyze 职责）保留；接口换新 ToolDefinition/ToolRegistry |
| 提醒规划（三档/quiet-hours/5 道防线） | reminders/ | **REWRITE** | plan_reminders 逻辑保留；调度后端换自研 APScheduler 接线 |
| 通知推送 + 桌面 toast | notifications/ | **REWRITE** | 文本组装/toast 保留；发送通道换新（不走 AstrBot Context） |
| NapCat 安装/配置/QR 向导 | — | **FUTURE** | 部署关注点，M7 后按需；V2 接入文档先写手动配置 |
| REST 路由语义（/tasks /sources /backup ...） | api/routers | **REWRITE** | 路由语义保留；宿主换独立 FastAPI；SSE 生命周期按新原则重写（B01/B02） |
| Pydantic schemas / 校验 | api/schemas | **REUSE_BEHAVIOR** | 校验模式照搬 |
| 备份/恢复（原子事务 + 排除敏感） | api/backup | **REUSE_BEHAVIOR** | 格式/流程保留 |
| 导入导出 transfer 格式 | api/transfer | **REUSE_BEHAVIOR** | 格式保留（含 V1 示例文件兼容） |
| 前端看板业务能力 | web/ | **REWRITE**（IA） | V1 单页看板功能清单作参照；全新 IA 与组件分层（12_WEB_UI_SPEC） |
| boardState.js 纯函数 | web/utils | **REUSE_BEHAVIOR** | 纯函数可带；**修 +8h 硬编码**（B12） |
| 群接入（star） | adapters/onebot | **REWRITE** | 自研 OneBotAdapter；bypass 契约（is_wake / is_at_or_wake_command 分离）语义保留 |
| provision（AstrBot 配置装配） | — | **DROP** | AstrBot 专属；V2 用自己 config/loader |
| persona 提示词 | agents/prompts | **REUSE_BEHAVIOR** | 文案保留 |
| replay（演示回放） | — | **FUTURE** | 非核心；M7 后按需 |

## 必须保留的行为约束（无论实现怎么变）

1. 通知"静默"语义：提醒不回源群（发到指定目标会话）
2. dismissed 任务仍算重复（防重新抽取）
3. 三级管道顺序不可颠倒（省 token 是第一原则）
4. 任务保留 source_text_reference 溯源（AI 有没有编的证据链）
5. 导入导出携带溯源、排除运行时字段

## 明确的丢弃

- AstrBot 全部 runtime（InitialLoader/EventBus/Pipeline/ProviderManager/PluginManager/star/dashboard）
- `import astrbot` 任何形式（Anti-AstrBot Gate 扫描）
- NapCat 一键安装向导（转为 FUTURE）
- provision 装配逻辑
- V1 前端整体（重新设计 IA）
