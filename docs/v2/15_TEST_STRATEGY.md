# 15_TEST_STRATEGY.md

> 测试策略。**测试通过 ≠ 项目正确**：必须区分验证层级（总根提示词第 7 条）。

## 验证层级定义

| 层级 | 定义 | 谁执行 |
|---|---|---|
| UNIT VERIFIED | 纯函数/单类，mock 隔离 | CI / 本机 |
| CONTRACT VERIFIED | 接口契约（OneBot JSON→CampusEvent、API schema、Tool schema） | CI / 本机 |
| INTEGRATION VERIFIED | 多模块真实协作（真 SQLite + mock 外部） | CI / 本机 |
| REAL ENV VERIFIED | 真实 NapCat + 真实 QQ + 真实 Provider | 验收阶段，人工/脚本 |
| VISUAL REVIEWED | 视觉审核 | 外部模型（最终） |
| NOT VERIFIED | 未验证 | — |

**禁止**：Mock 成功说成真实 QQ 成功；HTTP 200 说成业务正确；代码存在说成功能完成。

## 测试结构

```
tests/
├── unit/          # 纯逻辑：prefilter、timeresolve、dedup、converter、schemas
├── contract/      # 契约：OneBot 样例→CampusEvent、API schema、Tool 参数校验
├── integration/   # 真 SQLite：TaskService、ReminderService、ExtractionPipeline（mock LLM transport）
└── e2e/           # 全链路（M7）：fake NapCat → Adapter → Pipeline → DB → API → Web 状态
```

## 关键测试点（对齐风险，不为数量）

| 领域 | 必测 |
|---|---|
| OneBot Adapter | converter 真实 JSON 样例（群/私聊/text/at/reply/image/非 array 拒绝）；send 载荷格式；self-message 过滤 |
| EventBus / Router | 发布→分发→handler 异常隔离（一个 handler 崩不影响其他）；shutdown 清理 |
| TaskService | 唯一创建入口；dedup 409；deadline 变化重建提醒；状态流转 |
| Dedup | 组合指纹各分支；dismissed 仍算重复；explainable reason |
| Time Parser | 固定时钟/时区注入；"周五晚上12点"→23:59 等 V1 已验证约定全保留 |
| Extraction | **LLM 用可注入 transport（httpx.MockTransport 假响应）覆盖全路径**（B13：V1 从未测过 extract()）；schema 解析失败重试；畸形输出 |
| Reminder | resync 幂等；deadline 更新/complete/delete 联动；防重复调度；过期不补发 |
| Provider | 错误分类表（timeout/auth/rate_limit/...）各路径；结构化输出 |
| Tool Registry | 参数校验拒绝；超时；异常回填 |
| Agent Loop | max_steps 中止；重复 tool call 中止；tool 结果回填 |
| API | contract + integration；409/422/404 错误路径；auth（如有） |
| Realtime | SSE 连接生命周期；断线重连补拉；事件类型分离 |
| Migration | 空库创建；版本迁移 |
| 隔离 | `CAMPUSCUE_ENV=test` 断言；destructive 测试前置隔离证明 |

## Mock 策略

- LLM：**必须 mock 且可注入**（V2 修复 V1 缺口）——Provider transport 层注入，假响应走真实解析代码
- 平台：fake WS server（contract/e2e）
- DB：真实临时 SQLite（不 mock store；保留 aware/naive 边界测试）
- 时钟/时区：注入（禁 datetime.now() 直用）

## Visual Review Gate（M6）

- 浏览器自动化验证客观项：viewport / scroll / element bounds / overflow / console errors / 交互可达 / 无障碍（焦点、alt、label）
- 生成截图（1440/1024/768/390）→ `REVIEW_REQUEST.md` 标记 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`
- 外部审核通过前不宣称视觉正常

## REAL ENV 验收

- M1/M2/M3/M4/M7 各自的 REAL PASS 标准见 [17_MILESTONES](17_MILESTONES.md)
- 真实环境验收需独立数据/配置命名空间；完成后记录验证证据（时间、环境、消息样例、DB 查询结果）
