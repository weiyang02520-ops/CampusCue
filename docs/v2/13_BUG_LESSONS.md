# 13_BUG_LESSONS.md

> V1 Bug Inventory → V2 架构性预防。来源：V1 PROGRESS.md（七轮修复记录）+ 审计确认。每条标注状态：
> `ELIMINATED_BY_DESIGN`（架构上消除）/ `NEEDS_TEST`（需回归测试验证）/ `STILL_RELEVANT`（仍需注意）。

| # | Bug | Root Cause | V1 Fix | V2 Prevention | 状态 |
|---|---|---|---|---|---|
| B01 | SSE 断连日志洪水（数十万行，内存 4.6GB 卡死） | Python 3.12 ProactorEventLoop 在死 socket 上每次写 warning | SSE generator 捕获 GeneratorExit/ConnectionError/OSError/RuntimeError + log.py 提升 asyncio 日志级别 | Realtime 连接生命周期管理内置：cleanup 完整、重连指数退避、日志限频（22 Realtime 原则） | ELIMINATED_BY_DESIGN + NEEDS_TEST |
| B02 | SSE 状态不同步 / 断连无补拉 | 断连后前端无主动刷新 | 浏览器恢复联网后全量补拉 | SSE 仅通知；断线重连必须 REST 全量 refresh canonical state | ELIMINATED_BY_DESIGN |
| B03 | 看板"新建"重复创建 | API 路径只算 dedup_key 未查重，LLM 工具路径有查重——两条创建路径不一致 | API 查重返回 409 + 前端 saving 防连点 | **TaskService 唯一创建入口**（API/Tool/Pipeline 全走它，去重收敛一处） | ELIMINATED_BY_DESIGN + NEEDS_TEST |
| B04 | 首次加载群竞态 | 前端加载时序 | 修复 + 4 项 Node 状态测试 | WebUI 状态机 + 自动测试（M6） | NEEDS_TEST |
| B05 | 提醒事件污染任务卡片 | SSE 提醒事件与任务事件混用 | 区分事件类型 | Realtime 事件类型明确分离（task.* / reminder.* / extraction.* / connection.*） | ELIMINATED_BY_DESIGN |
| B06 | 乐观操作失败未回滚 | 前端乐观更新无失败处理 | 失败回滚 + 测试 | 乐观更新失败回滚为标准模式 + 测试（M6） | NEEDS_TEST |
| B07 | 测试实例污染真实数据 | 测试实例未用独立数据目录，删除/恢复测试误清真实演示数据 | 统一 ASTRBOT_ROOT 独立目录 | **CAMPUSCUE_ENV=test 硬性断言数据目录隔离**（18 测试隔离）；destructive 测试前置隔离证明 | ELIMINATED_BY_DESIGN + NEEDS_TEST |
| B08 | 端口冲突 / 状态不同步 | 多实例与启动顺序 | 进程所有权校验 | Runtime 单一实例生命周期；启动端口占用预检（07） | NEEDS_TEST |
| B09 | 对话框焦点管理缺陷 | 弹窗未聚焦，键盘/读屏用户停留触发按钮 | nextTick 聚焦 dialog | 无障碍为 M6 自动测试验收项 | NEEDS_TEST |
| B10 | 导入/恢复半状态 | 恢复无原子性 | 单事务替换 5 表 + 失败回滚测试 | 恢复保持单事务原子替换（09） | ELIMINATED_BY_DESIGN + NEEDS_TEST |
| B11 | 模型格式错误响应泄漏 | 完整模型响应存溯源库，异常日志复制正文 | 仅存本机溯源库，日志不复制 | 日志脱敏为设计约束（16）+ 回归测试 | NEEDS_TEST |
| B12 | 时区硬编码（审计新发现） | CAMPUS_TZ 模块常量 + 前端 +8h 硬编码（boardState.js:3） | V1 未修（仅默认 Asia/Shanghai 可用） | TimeNormalizer 显式 timezone 注入；API 返回 aware ISO 时间；前端不硬编码偏移 | STILL_RELEVANT（M2 必修） |
| B13 | LLM 测试无真实覆盖（审计新发现） | extract() 从未在测试里跑过（LLM 不 mock） | — | V2 测试策略：LLM 用可注入 transport mock（httpx.MockTransport 假响应）覆盖结构化解析全路径 | STILL_RELEVANT（M2 建测试时修） |

## 方法论要求

- 每个 Bug 修复必须留下：root cause / fix / regression test（总根提示词第 8 条）
- 重要 Bug 修复同步更新本表
- 新 Bug 出现：先记录现象/复现/错误/影响/候选原因，再定位，禁止连环乱改
