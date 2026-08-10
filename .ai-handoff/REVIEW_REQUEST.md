# REVIEW_REQUEST.md

> M2b.2 REAL ENV ACCEPTANCE 最终审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue`（HEAD：M2b.2 验收轮）复核本轮真实环境证据。

## 背景

M2b.1（AI-first pipeline）外部最终 PASS 后，M2b.2（真实 Provider + 真实 QQ + 真实 SQLite 验收）已完成。**本轮零 CampusCue 源码修改**（纯验收轮）。

## 请求审核内容（10 项 M2b.2 复核点）

1. **REAL QQ 群消息完整链路**：真实群消息 → NapCat（Framework）→ Reverse WS（127.0.0.1:6199）→ CampusEvent → SourcePolicy → AI-first pipeline → 真实 DeepSeek Provider → TimeNormalizer/Dedup/TaskService → 真实 SQLite Task 行
2. **structured_mode = json_fallback**：DeepSeek 拒绝 json_schema → CampusCue 正确回退（共享 canonical 语义契约，≤2 calls）
3. **deadline 精确**：`2026-08-14 15:59 UTC`（= 2026-08-14 23:59 Asia/Shanghai，`weekday+clock` 规则）
4. **provider/model provenance**：Extraction 行 `openai_compatible` / `deepseek-chat`
5. **普通聊天 → skipped**：真实 `hello` 到达 Provider，has_task=false → skipped Extraction，无 Task，无输入文本泄漏（normalized/audit 无原文）
6. **语义重复**：重复任务消息 → `same_semantic_task` duplicate，Task 数保持 1
7. **重启持久化**：仅重启 CampusCue → NapCat 自动重连（`onebot client connected`），Task 仍在（DB 业务事实）
8. **M1 共存**：M2 pipeline 启用时 `hello` → `received: hello`（send_group_msg retcode 0）
9. **用户大号保护**：测试全部用独立小号 bot；用户大号未触碰、配置已还原默认
10. **零源码修改**：无 CampusCue source changes

## 真实环境证据（Workspace Agent + USER）

- **[MACHINE_CONFIRMED]**：WS ESTABLISHED 稳定 65s+；CampusCue 日志 `onebot client connected`；send_group_msg retcode 0；SQLite Task/Extraction 行（deadline/provider/model/audit）
- **[USER_CONFIRMED]**：用户提供群聊时间线（20:57:47 任务消息 → 20:58:00 received:hello → 20:58:28 重复任务）
- REAL MODEL VARIANCE：course 提取依赖消息原文是否含课程名（"数第三章"原文 → null；"高数第三章" → 高等数学）——确定性代码正确，不加模糊匹配

## 风险与未验证项（诚实声明）

- 真实 Provider = DeepSeek `deepseek-chat`（OpenAI-compatible）；structured_mode=json_fallback
- NapCat Framework 启动需 stdout 重定向（否则 EPIPE 终端问题）；WS 曾断开（`Object has been destroyed`）后重连恢复
- prompt-injection 为 mock/契约级防御纵深，不宣称真实免疫

## Real Verified vs Not

- **CONFIRMED（REAL ENV）**：完整真实链路、deadline 精确、去重、重启持久化、M1 共存、privacy
- **NOT VERIFIED**：无（M2 范围内全部真实验证）；M3+ 未开始

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
