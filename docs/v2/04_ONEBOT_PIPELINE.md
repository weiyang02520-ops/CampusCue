# 04_ONEBOT_PIPELINE.md

> OneBot v11 收发管线设计（M1 实现）。基于 AstrBot 已验证调用链（[03_ASTRBOT_ARCHITECTURE](03_ASTRBOT_ARCHITECTURE.md) §4），但实现自研、轻量。
> 本文件已按 M0.1 外部审核修正 Reverse WS 所有权与帧关联模型。

## 部署形态

```
QQ ←→ NapCat（QQ 协议侧）
NapCat ──OneBot v11 Reverse WebSocket──► CampusCue OneBotAdapter
                                         (WebSocket SERVER, e.g. ws://127.0.0.1:6199/ws)
```

**连接所有权（重要）**：
- **NapCat = Reverse WebSocket CLIENT**（主动拨入）
- **CampusCue = Reverse WebSocket SERVER**（监听并接受连接）
- 因此 CampusCue **不做"向 NapCat 指数退避重连"**——那不是本方案行为。

断线恢复模型（NapCat 主动重连）：

```
NapCat disconnect
  → CampusCue detects disconnect
  → clean old connection / pending actions（fail 全部 pending Future）
  → server 继续监听
  → NapCat reconnects
  → CampusCue accepts new connection
  → 替换 stale active connection
  → resume
```

Server 配置（M1）：
- configurable host（默认 `127.0.0.1`）/ port（默认 `6199`）/ path
- configurable access token（OneBot 协议可选）；配置后校验 NapCat 请求头 token，**token 永不进日志**
- M1 单 active connection；新连接替换旧连接（stale replacement）
- disconnect cleanup；日志限频（V1 教训：WS 断连日志洪水）；graceful shutdown（关闭监听 + 清理连接）

## Receive Pipeline（M1 范围：text 完整，at/reply/image 解析到段）

```
NapCat
  → WS frame (OneBot v11 JSON)
  → OneBotAdapter._on_frame(json)          # Adapter 边界：OneBot JSON 在这里被消化
  → 帧分类（见下：Event Frame vs Action Response Frame）
  → converter.parse_payload(json)          # → CampusEvent（核心转换，纯函数可单测）
  → transport-level dedup（self_id, message_id）
  → bus.publish(event)                     # 有界队列，背压
  → Router.route(event)
  → Handler（M1: EchoHandler；M2: TaskPipeline；M4: AgentChat）
  → OutgoingMessage → dispatcher → Adapter.send()
```

### 帧分类（E，M1 必须正式设计）

同一 Reverse WebSocket 承载两种帧，**必须区分**：

| 帧类型 | 判定 | 处理 |
|---|---|---|
| **Event Frame** | OneBot 事件推送（`post_type` 存在，如 `message`） | → converter → CampusEvent → bus |
| **Action Response Frame** | 对 Outbound Action 的响应（含 `echo` 字段） | → 不产生 CampusEvent；关联 pending Future（见下） |

**禁止把 Action Response 当 CampusEvent 处理。**

### Outbound Action 关联（echo correlation）

采用同一 Reverse WebSocket 完成 M1 outbound actions（不另开连接）。发送流程：

```
create unique echo (uuid)
  → register pending Future[echo]（map，带超时）
  → send OneBot action request（JSON 含 echo）
  → 等待 WS frame
  → if frame 是 action response 且 echo 匹配 → resolve pending Future → return success/data/error
```

- 支持 action：`send_group_msg`、`send_private_msg`
- 要求：**action timeout**（如 10s）、**pending map cleanup**（完成/超时/断连即清理）、**disconnect → fail all pending actions**、**duplicate / unknown echo 安全处理**（未知 echo 静默丢弃并记日志限频）
- 发送路径：`Service/Agent 产出 → OutgoingMessage(text) → dispatcher → Adapter.send(conversation_id, conversation_type, text) → WS action + echo → 等待响应`
- M1 只实现 text 段发送；后续（M2+ 按需）：at（后插空格防粘连）、reply、image

## Guard（M1 范围，见 H 修正）

M1 Guard 不依赖 source-enabled（SourcePolicy 从 M2 开始，M1 无 SourceRepository/Service）。M1 只需要：

- valid message（格式/字段校验）
- self-message suppression（`user_id == self_id`，Adapter 内完成 + Guard 兜底）
- **duplicate suppression（transport-level dedup，见下）**
- minimal rate/backpressure safeguards

## Transport-level Dedup（G，M1）

- key：`(self_id, message_id)`
- 目的：NapCat reconnect / duplicate delivery 时同一消息短时间不被执行两次（Echo / future handler）
- **transport-level idempotency，与 M2 Task semantic dedup 完全无关**
- 要求：bounded memory（如容量上限 10k）、TTL（如 5 分钟）、testable clock
- 实现极小

## EventBus Backpressure（F，M1）

- `asyncio.Queue(maxsize=configured_small_bound)`（如 256）
- `publish` 使用 `await queue.put(...)` → ingress 过载时产生背压（有界，不无限堆积）
- dispatch：每事件独立 Task + 强引用集合（防 GC）+ 异常隔离（handler 崩不影响总线）
- shutdown：cancel + drain 策略明确（见 07_RUNTIME_LIFECYCLE）
- 不做 Kafka/Redis/RabbitMQ

## 状态与自检

- Adapter 暴露 `status()`：listening / connected / disconnected + last_event_at + last_error
- 心跳/连接状态进 `GET /api/health` 与接入页（M5/M6）
- 断线恢复后：无需重放事件（事件只在内存管道，DB 是事实源）

## 契约测试（M1 验收）

- converter 纯函数：真实 OneBot JSON 样例（群/私聊/text/at/reply/image 组合）→ 期望 CampusEvent 字段
- 帧分类：Event Frame vs Action Response Frame 判定
- echo correlation：假 WS client 发 action → 匹配 echo → 返回；超时/断连 → pending fail
- WS 层：fake WS server/client 收发一次 text，验证 send_group_msg 载荷格式
- 不依赖真实 NapCat（REAL ENV VERIFIED 在验收阶段单独做）
