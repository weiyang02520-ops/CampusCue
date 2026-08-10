# CampusCue V2 — M1 Runtime

独立 QQ 运行闭环（NapCat / OneBot v11），**不依赖 AstrBot**。

> 当前能力仅 M1（Echo）：真实 QQ 群/私聊发 `hello` → 回复 `received: hello`。
> M2+ 功能（任务抽取/提醒/WebUI）尚未实现，不在此文档描述。
>
> **开发者注（M2b.2）**：数据层 + Provider Foundation（M2a）+ Task Extraction Pipeline（M2b.1：L0-L7）已完成；**M2b.2 真实环境验收通过**（真实 QQ 群消息 → NapCat → Reverse WS → AI-first pipeline → 真实 Provider → SQLite Task）。
>
> **启用方式**：`CAMPUSCUE_TASK_PIPELINE=1` + `CAMPUSCUE_DB_PATH=<验收 DB>` + `CAMPUSCUE_TIMEZONE=Asia/Shanghai`。真实 Provider 配置见 `scripts/m2_configure_provider.py`（secret 只存 env 变量名）；真实来源配置见 `scripts/m2_configure_source.py`（conversation ID 走 `CAMPUSCUE_SOURCE_CONVERSATION` 环境变量，不写 Git）。
>
> **真实环境验证事实（2026-08-10，M2b.2）**：
> - 真实群消息"高数第三章作业周五晚上12点前交学习通"→ Task（deadline 精确 `2026-08-14 15:59 UTC`）
> - 真实 DeepSeek `deepseek-chat`：**structured_mode=json_fallback**（json_schema 不支持时 CampusCue 自动回退 JSON-only，共享同一语义契约）
> - 普通聊天 → skipped Extraction 无 Task；重复任务 → 语义去重不创建第二 Task；重启 CampusCue 后 NapCat 自动重连、Task 持久化
> - NapCat Framework 启动：**必须把 stdout/stderr 重定向到文件**（前台终端可能触发 EPIPE broken pipe）；注入命令 `napimain.exe <QQ路径> <napiloader.dll> <nativeLoader.cjs>`

## 架构

```
QQ ←→ NapCat（CLIENT，反向 WS 拨入）→ CampusCue OneBotAdapter（SERVER，127.0.0.1:6199/ws）
  → CampusEvent → EventBus（有界队列 + 有界并发）→ Router → EchoHandler → 回复
```

## 安装与运行（真实环境验证过的步骤）

### 1. 创建独立 V2 环境（重要）

仓库根目录同时存在 Legacy `campuscue/`（AstrBot fork），**不要**在仓库根直接 `python -m campuscue`（import 会被 Legacy 遮蔽）。

```bash
cd v2
python -m venv .venv-m1-real
.venv-m1-real/Scripts/pip install -e .

# 确认 import 来自 v2/src（不是 Legacy）：
.venv-m1-real/Scripts/python -c "import campuscue; print(campuscue.__file__)"
# 应输出 ...\v2\src\campuscue\__init__.py
```

### 2. 启动 CampusCue

**推荐 PowerShell**（Windows 真实环境）：

```powershell
cd v2
$env:CAMPUSCUE_ONEBOT_HOST = "127.0.0.1"
$env:CAMPUSCUE_ONEBOT_PORT = "6199"
$env:CAMPUSCUE_ONEBOT_PATH = "/ws"
$env:CAMPUSCUE_ONEBOT_TOKEN = "<临时随机 token>"   # 与 NapCat 配置一致
$env:CAMPUSCUE_DIAGNOSTIC = "1"                    # 仅联调诊断；生产不要开
.venv-m1-real\Scripts\python.exe -m campuscue
```

**Git Bash**（注意 MSYS 路径转换陷阱）：

```bash
cd v2
export MSYS_NO_PATHCONV=1                       # 必须！否则 /ws 会被转成 C:/Program Files/Git/ws
export CAMPUSCUE_ONEBOT_HOST=127.0.0.1
export CAMPUSCUE_ONEBOT_PORT=6199
export CAMPUSCUE_ONEBOT_PATH=/ws
export CAMPUSCUE_ONEBOT_TOKEN=<临时随机 token>
export CAMPUSCUE_DIAGNOSTIC=1
.venv-m1-real/Scripts/python.exe -m campuscue
```

> 已知真实环境陷阱（M1.2 实测）：Git Bash 会把 `/ws` 这类以 `/` 开头的参数做 MSYS 路径转换，变成 `C:/Program Files/Git/ws`，导致启动失败（`invalid path`）。**必须 `export MSYS_NO_PATHCONV=1`**，或改用 PowerShell/cmd。

日志显示 `onebot reverse ws server listening on ws://127.0.0.1:6199/ws` 即就绪。

### 3. 配置 NapCat（反向 WS 客户端）

NapCat 登录后配置文件在 `NapCat目录/config/onebot11_<QQ号>.json`（或 WebUI 创建）：

```json
"network": {
  "websocketClients": [{
    "name": "campuscue-v2-m1",
    "enable": true,
    "url": "ws://127.0.0.1:6199/ws",
    "messagePostFormat": "array",      // 必须显式 array（勿依赖默认值）
    "reportSelfMessage": false,
    "reconnectInterval": 5000,
    "token": "<与 CAMPUSCUE_ONEBOT_TOKEN 一致>"
  }]
}
```

### 4. 验证

- 用**非 Bot 的另一个 QQ** 在群里/私聊发 `hello`（纯文本）
- Bot QQ 应回复 `received: hello`
- 发普通消息不会收到回复（EchoHandler 只响应精确 `hello`）
- 重启 CampusCue 后 NapCat 会自动重连（默认 5s）

## 隐私注意事项

- 默认只监听 `127.0.0.1`；`CAMPUSCUE_ONEBOT_TOKEN` 只放环境变量/本地配置，**永不提交 Git**
- 正常日志脱敏（不记录 QQ 号/群号/消息正文）；`CAMPUSCUE_DIAGNOSTIC=1` 仅联调用，真实 ID 不入库不入 Git
- NapCat 的 QQ 登录态、config、logs 都在仓库外（如 `C:\Tools\NapCat\`），不入 Git

## 测试

```bash
cd v2
PYTHONPATH=src python -m pytest tests/ -q
python scripts/check_no_astrbot.py   # Anti-AstrBot Gate
```

## 环境要求

- Python ≥ 3.12
- 运行时依赖仅 `websockets`（M1 实测版本 16.0 / Python 3.14）
- NapCat（官方 Release）：M1.2 实测 `v4.18.18` Framework 版注入式
