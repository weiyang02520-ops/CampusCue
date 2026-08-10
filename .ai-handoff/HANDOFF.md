# HANDOFF.md

> 当前操作状态（canonical）。历史里程碑细节见 CHANGELOG_AI.md 与 CHATGPT_MEMORY.md HISTORY。

## 当前（M1.3 Continuity & Privacy Cleanup）

- **本轮**：外部审核确认 M1 技术全部 PASS 后，执行连续性/隐私清理（8 项 finding 修复）
- **状态**：M1.3 CONTINUITY_PRIVACY_FIX_COMPLETE — AWAITING_EXTERNAL_REVIEW
- **Gate**：M1 = PASS；M2 = READY_NOT_STARTED / NOT_AUTHORIZED（等 M1.3 外部确认）

## 本轮完成

1. **Finding A（隐私）**：当前树中真实 Bot QQ 标识符已全部语义脱敏（`onebot11_<BOT_QQ_REDACTED>.json`）；测试群名称脱敏
2. **Finding B**：CHATGPT_MEMORY 顶部 CURRENT TRUTH 更新为 M1 PASS 后的真实世界状态（M2 READY_NOT_STARTED）
3. **Finding C**：AGENT_MEMORY Gate 矛盾修复（M1 PASS / M1.3 当前 / M2 NOT_AUTHORIZED）
4. **Finding D**：v2/README.md 补 Git Bash MSYS_NO_PATHCONV workaround + PowerShell/Git Bash 分块
5. **Finding 10**：本文件重构为 canonical（不再无限追加）
6. **MEMORY DELTA 5 条**写入双 Memory（含 PII 隐私教训）

## PRIVACY_NOTE

- 一个真实 QQ 标识符（NapCat 配置文件名）曾在 M1.2 HANDOFF 中被意外提交，已在当前 HEAD 脱敏。
- **历史提交仍含该标识符；未做历史重写**（rebase/filter-repo/force push 需要显式用户授权，未执行）。

## 历史摘要（详情见 CHANGELOG_AI.md）

| Milestone | 状态 |
|---|---|
| M0 / M0.1 / M0.2 | PASS（研究 + 审计 + 文档 + 修复） |
| M1 | PASS（独立 QQ Runtime 实现，commit 9bfb018） |
| M1.1 | PASS（外部 correctness 审核 8 项修复，commit 71f7f99） |
| M1.2 | PASS（REAL ENV VERIFIED：NapCat v4.18.18 + 真实 QQ hello→received:hello 等，commit 7ae0810） |
| M1.3 | 本轮（清理，commit 待定） |

## REAL ENV 事实（保留，ID 脱敏）

- NapCat 官方 **v4.18.18**；NapCat = Reverse WS CLIENT；CampusCue = Reverse WS SERVER（127.0.0.1:6199/ws）
- token handshake 成功；messagePostFormat=array 真实兼容
- 真实群聊 + 私聊 `hello` → `received: hello`（action retcode 0 + 用户确认）
- 非 hello 消息无回复；CampusCue 重启后 NapCat 自动重连且 hello 继续工作
- lifecycle/heartbeat 帧被业务路由安全忽略

## 本轮修改文件

- .ai-handoff/HANDOFF.md（canonical 重写 + 脱敏）
- docs/context/CHATGPT_MEMORY.md（CURRENT TRUTH 修复 + §9E）
- docs/context/AGENT_MEMORY.md（Gate 修复 + PII 失败模式）
- v2/README.md（Git Bash workaround + shell 分块）
- .ai-handoff/ 其余 5 文件

## AGENT_DISCOVERED_DELTA

- None beyond externally requested M1.3 corrections.

## 下一步

- 外部 ChatGPT 复核 M1.3 → M2 授权
