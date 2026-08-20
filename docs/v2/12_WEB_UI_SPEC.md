# 12_WEB_UI_SPEC.md

> CampusCue V2 WebUI 规格。M0 只设计：信息架构、页面职责、状态归属、交互与响应式规则、设计系统原则。
> **禁止**：拍具体颜色/渐变/声称视觉漂亮。最终视觉审核由外部模型完成（VISUAL REVIEW REQUIRED BY EXTERNAL MODEL）。

## 信息架构

主导航（V2 全新 IA，不复用 V1 单页看板）：

```
首页         任务        消息        日历        AI 助手
──────      ────      ────      ────      ──────
                接入        模型        设置
```

## 页面职责

### 首页
- 回答"我今天有什么事情？"
- 第一屏：今天的任务、即将截止、本周安排、最近识别、QQ 连接状态、AI Provider 状态
- 禁止优先展示 CPU/RAM/token 等开发者指标

### 任务页
- 视图：今天 / 本周 / 以后 / 已完成
- 支持：搜索、过滤（category/course/source）、手动创建、编辑、完成、忽略
- 任务卡重点：标题、课程/类型、截止、来源、状态
- 移动端：卡片列表；桌面端可列表/卡片

### 消息页
- 不是完整 QQ 客户端；展示 CampusCue 处理过的校园信息
- 每条：原消息、来源群、识别时间、提取结果、创建的任务、未创建原因、置信度

### 日历页
- Deadline Calendar：按任务截止时间展示
- 第一版不做复杂 Outlook 式功能

### AI 助手页
- 正常聊天体验；用户提问 → Agent → Tool → 真实数据 → 回答
- 展示 tool 调用状态（可折叠，如"正在查询任务…"）

### 接入页（Connections）
- NapCat / OneBot 连接状态、配置、自检、最近事件
- 高级原始 JSON 放"诊断"折叠区，不默认暴露

### 模型页（Providers）
- Provider 列表、Base URL、Model、Secret（secret_reference 编辑，不显示真实值）、测试连接
- 高级参数折叠

### 设置页
- 提醒偏好、隐私/消息保留策略、数据（备份/恢复/导入导出）、主题（light/dark）、诊断

## 状态归属

| 状态 | Owner |
|---|---|
| 任务/来源/提醒等业务数据 | Pinia store（fetch 后缓存；REST 为事实源） |
| 认证态 | Pinia（M5 定） |
| SSE 连接生命周期 | composable `useRealtime`（连接/退避/断线补拉） |
| 表单本地态 | 组件局部 state |
| 路由 | Vue Router |

规则：**SSE 只通知，收到通知后按需 REST 刷新**；断线重连后全量 refresh canonical state（V1 B02/B05 教训）。

## 关键交互（含无障碍要求）

- 弹窗打开：焦点移入 dialog 容器（`tabindex="-1"` + nextTick focus），Escape 关闭，可 Tab 遍历（V1 B09 教训）。
- 乐观更新：失败必须回滚 + 提示（V1 B06 教训）。
- 创建防连点：`saving` 态禁止重复提交（V1 B03 教训）。
- 空状态：清晰说明 + 行动引导（非装饰性 Emoji）。

## 响应式规则

| 断点 | 布局 |
|---|---|
| ≥1024 | 桌面：侧边栏导航 + 内容区 |
| 768-1023 | 平板：侧边栏可折叠 |
| <768 | 移动：底部导航或汉堡菜单；表格→卡片；任务卡单列 |
| 390 | 必须完成核心操作：查看任务、完成、新建、设置 |

要求：390px 无横向溢出；Dialog 宽度适配；表单流式换行。执行模型用浏览器自动化验证 viewport/bounds/overflow/console errors。

## 设计系统原则（M0 只定原则，M6 定具体值）

- **Design Tokens** 统一管理：color roles（bg/surface/border/text/primary/accent/success/warning/danger）、spacing scale（4px 基准）、radius scale、typography（字号阶梯）、shadow、motion（短时、克制）。
- Light + Dark 双主题；语义色统一（成功/警告/危险不用多个自定义色值）。
- 禁止每页自定义一套颜色。
- 图标：统一 Lucide（或全站唯一 SVG 库）；禁止 Emoji/颜文字。
- 克制动画：仅状态变化与弹层使用，无炫技。
- 避免：到处渐变、发光紫球、AI 机器人头像、宇宙背景、巨型 Hero、玻璃拟态满屏、每卡不同色、过度圆角。

## 技术栈

Vue 3 + TypeScript + Vite + Vue Router + Pinia + Lucide（M6 实现，见总根提示词 6.24）。

## 视觉审核 Gate

- M6 生成桌面/移动（1440/1024/768/390）真实截图，提交 `REVIEW_REQUEST.md`：
  `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`
- 审核通过前不宣称"视觉正常"。

## M6 implementation addendum (2026-08-20)

- `v2/web/` is the implemented Vue 3 + TypeScript + Vite workspace. It uses Vue Router, Pinia, and Lucide icons.
- Implemented routes: Home, Tasks, Messages, Calendar, Agent, Connections, Providers, Settings.
- M5 REST remains canonical for initial loads and mutations. `/api/v1/stream` is notification-only; reconnect uses bounded exponential backoff and refreshes REST state.
- Task completion/dismissal uses optimistic UI with rollback on failure. Agent tool activity is rendered only when the backend returns non-empty `tool_activity`; no fake tool animation is emitted.
- Light/dark semantic tokens, desktop sidebar, mobile bottom navigation, no-emoji controls, visible focus, labeled fields, no horizontal overflow, and synthetic Playwright fixtures are implemented.
- External integration review requested `M6 = CHANGES_REQUESTED`; this checkpoint completes `M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`. Screenshots and real M5 integration evidence require external review before `M6 FINAL`.
