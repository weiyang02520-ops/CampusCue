# HANDOFF.md

> M1 Independent QQ Runtime 交接记录。由工作区 AI 在 checkpoint 前更新。

## 本轮目标

实现 M1：完全不依赖 AstrBot 的 CampusCue V2 QQ 最小运行闭环（QQ → NapCat → OneBot v11 Reverse WS → OneBotAdapter → CampusEvent → EventBus → Router → EchoHandler → 回复）。**M1 范围只做这个，未实现任何 M2 内容。**

## 本轮完成

### V2 独立实现根（ADR-011）

- `v2/` 独立 implementation root：`v2/src/campuscue/` + `v2/tests/` + `v2/scripts/`
- Legacy `campuscue/` / `astrbot/` / `dashboard/` 冻结（git diff 验证零改动）
- pyproject：runtime 依赖仅 `websockets`；测试依赖 pytest + pytest-asyncio

### 实现模块（v2/src/campuscue/）

| 模块 | 职责 |
|---|---|
| core/events.py | CampusEvent（ID 全 str、时间 UTC-aware、MessageSegment 保序） |
| core/bus.py | EventBus：有界队列（await put 背压）+ 有界 in-flight（semaphore）+ handler 异常隔离 + shutdown drain |
| core/router.py | 最小路由（event type 校验 + stateless self-message 防御 + EchoHandler 选择） |
| core/outbound.py | OutgoingMessage（平台中立，业务层不构造 OneBot action） |
| handlers/echo.py | EchoHandler：仅响应 trimmed text == `hello` → `received: hello`（非复读机） |
| adapters/base.py | PlatformAdapter 边界（start/stop/send/status，刻意小而直） |
| adapters/onebot/adapter.py | Reverse WS SERVER：token 校验、帧分类、converter 入站、canonical dedup（self→dedup→publish）、echo correlation（register-before-send、timeout/pending cleanup/断连 fail-all）、generation 竞态保护 |
| adapters/onebot/converter.py | 纯函数转换 + 帧分类（EVENT/ACTION_RESPONSE/IGNORED_META/UNKNOWN） |
| adapters/onebot/protocol.py | action 构建 + 响应校验（typed ActionError，仅安全字段） |
| adapters/onebot/dedup.py | transport dedup（bounded + TTL + testable clock） |
| app/runtime.py | CampusRuntime 状态机（CREATED→STARTING→RUNNING→STOPPING→STOPPED/FAILED），M1 只 wiring Config/Router/EventBus/Adapter/Echo |
| config.py | 最小配置（host/port/path/token env/queue/in-flight/action timeout/pending bound/dedup） |
| __main__.py | `python -m campuscue` 入口（Ctrl+C 优雅 shutdown） |

### 安全

- 默认仅监听 127.0.0.1；非 loopback host 启动即 FAIL（M1 不做 LAN 安全）
- access token：env（CAMPUSCUE_ONEBOT_TOKEN）读取，handshake 校验，永不打印/进日志
- 日志 NORMAL MODE 脱敏（不记录 QQ ID/群号/消息正文）；`CAMPUSCUE_DIAGNOSTIC=1` 显式诊断模式（默认 OFF，仅验收用）

### 测试

- **UNIT 49 passed**：converter（group/private/多 text/at/reply/image/保序/ID 字符串/时区/缺字段/非 array/unsupported/无效载荷）、帧分类、dedup（首条/重复/TTL/容量/不同 self_id/clock）、bus（有界队列/背压阻塞/并发上限/异常隔离/shutdown 各态/无孤儿任务）、action correlation（成功/retcode 错误/超时/断连/未知 echo/重复 echo/pending cleanup/max bound）、connection generation（stale cleanup 不清新连接、旧 pending 失败、新连接正常）
- **INTEGRATION 16 passed**（fake NapCat 全链路，ephemeral port）：group hello 完整链路（action/params/message/echo/响应解析）、private hello、duplicate 单 action、self-message 无回复、非 hello 真实流量无回复、第二连接替换第一、token 拒绝/接受、无效数据韧性（坏帧后 hello 仍工作）、断连 pending 立即失败+重连恢复
- **PACKAGE ISOLATION PASS**：fresh venv 安装 v2/ → import campuscue → 模块全部可导入（不依赖 Legacy root / AstrBot）
- **Anti-AstrBot Gate PASS**：AST 扫描 0 个 astrbot import、依赖 0、隔离 smoke OK

### REAL ENV

- **NOT VERIFIED**：本机无 NapCat（仅 QQ 客户端）。未伪造 PASS。

## 实际修改文件

- 新增：v2/（pyproject + src/campuscue/* + tests/* + scripts/check_no_astrbot.py）
- 新增：docs/v2/adr/ADR-011_V2_CODE_ISOLATION.md
- 修改：docs/v2/18_DECISIONS.md（ADR-011 索引）、04_ONEBOT_PIPELINE.md（canonical dedup 点 + 帧分类表 + Guard）、17_MILESTONES.md（M1 验收语义 + diagnostic mode + 状态定义）
- 修改：docs/context/CHATGPT_MEMORY.md（§9B M1 MEMORY DELTA + 时间线）、AGENT_MEMORY.md（§2 状态 + §18）
- 修改：.ai-handoff/ 6 文件

## 真实测试

- 65 tests 全绿（pytest）；fresh venv 隔离安装验证通过；Anti-AstrBot Gate 通过
- REAL ENV：未执行（无 NapCat）

## Mock Tests / 未验证

- 真实 QQ hello → received: hello 链路未验证（阻塞：无 NapCat）
- 真实 NapCat token handshake 行为未确认（按 OneBot 协议标准实现）

## AGENT_DISCOVERED_DELTA

- [REPO_FACT]：本机无 NapCat（AppData/Desktop 搜索 + tasklist 确认），仅 QQ 客户端在运行 → REAL ENV 验证被阻塞。
- [REPO_FACT]：websockets 16.0（Python 3.14.4 环境）API 为 `serve(handler, host, port)` + `ServerConnection.recv/send`；实现已按此版本适配。
- [DESIGN_CONFLICT]：M0 设计"converter 作为 WS server 连接处理"与 websockets 16 的 `process_request` token 校验点：token 校验在 handshake 阶段（process_request），帧处理在 connection handler——实现已分层处理。
- [UNVERIFIED_HYPOTHESIS]：NapCat 默认 `message.post-format` 为 array（converter 拒绝 string 格式）；真实环境需确认。

## Known Bugs

- 无已知新 Bug（M1 范围内）。V1 遗留 B12/B13 待 M2 修。

## Architecture Changes / Decisions

- ADR-011（V2 代码隔离）；MEMORY DELTA 7 条入双 Memory（§9B）

## Branch / Remote / Base

- 仓库：weiyang02520-ops/CampusCue（public）
- 本次提交：feat: implement independent M1 QQ runtime
- Base：2014a78（M0.2 commit）

## External Review Focus

- 见 REVIEW_REQUEST.md（15 项审核点）
