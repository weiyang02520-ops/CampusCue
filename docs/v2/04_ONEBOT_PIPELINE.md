# 04_ONEBOT_PIPELINE.md

> OneBot v11 收发管线设计（M1 实现）。基于 AstrBot 已验证调用链（[03_ASTRBOT_ARCHITECTURE](03_ASTRBOT_ARCHITECTURE.md) §4），但实现自研、轻量。

## 部署形态

```
QQ ←→ NapCat（QQ 协议侧）
NapCat ──OneBot v11 Reverse WebSocket──► CampusCue OneBotAdapter
                                         (WebSocket server, e.g. ws://127.0.0.1:6199)
```

- NapCat 以反向 WS 客户端身份连接 CampusCue 的 WS server（NapCat 配置 `onebot11.json`：ws-reverse + 目标地址）
- 第一版单连接、单适配器；连接生命周期：指数退避重连（1s→2s→4s→…→60s 封顶）、日志限频（V1 教训：WS 断连日志洪水）

## Receive Pipeline（M1 范围：text 完整，at/reply/image 解析到段）

```
NapCat
  → WS message (OneBot v11 JSON: post_type=message, message_type=group|private)
  → OneBotAdapter._on_message(json)         # Adapter 边界：OneBot JSON 在这里被消化
  → converter.parse_payload(json)           # → CampusEvent（核心转换，纯函数可单测）
  → bus.publish(event)
  → Router.route(event)
  → Handler（M1: EchoHandler；M2: TaskPipeline；M4: AgentChat）
  → Response 经 bus → Adapter.send()
```

### CampusEvent 转换规则（M1）

| OneBot 字段 | CampusEvent | 说明 |
|---|---|---|
| `message_id` | message_id | |
| `group_id` / `user_id` | conversation_id + conversation_type | group→群号，private→QQ 号 |
| `sender.user_id` / `sender.card` | sender_id / sender_name | |
| `time` | timestamp | |
| `message[]` | text + segments | array 格式要求；text 段拼合；at/reply/image 解析到 segments；**非 array 格式拒绝并告警**（V1/AstrBot 一致） |
| `raw_message` | metadata.raw | 调试引用，不进业务 |

- 拒绝 self-message（`user_id == self_id`）在 Adapter 内完成（Guard 也兜底）
- 私聊/群聊双通道；第一版不处理 notice/request 事件（M1 明确不做：好友事件、群事件、文件上传等）

## Send Pipeline（M1 范围：text）

```
Service/Agent 产出 → OutgoingMessage(text)
  → Adapter.send(conversation_id, conversation_type, text)
  → WS action: send_group_msg / send_private_msg（OneBot v11 JSON）
  → NapCat → QQ
```

- M1 只实现 text 段发送
- 后续（M2+ 按需）：at（后插空格防粘连）、reply、image

## 状态与自检

- Adapter 暴露 `status()`：connected / connecting / disconnected + last_event_at + last_error
- 心跳/重连状态进 `GET /api/health` 与接入页（M6）
- 断线恢复后：无需重放事件（事件只在内存管道，DB 是事实源）

## 契约测试（M1 验收）

- converter 纯函数：真实 OneBot JSON 样例（群/私聊/text/at/reply/image 组合）→ 期望 CampusEvent 字段
- WS 层：fake WS server 收发一次 text，验证 send_group_msg 载荷格式
- 不依赖真实 NapCat（REAL ENV VERIFIED 在验收阶段单独做）
