# CHANGELOG_AI.md

> AI 变更日志（供后续模型追历史，不依赖聊天记录）。

## 2026-08-09 · M0

- **任务**：M0 Architecture / Audit（研究 AstrBot 固定基准 + 审计 V1 + V2 设计文档）
- **Commit**：`6480ad2` docs: M0 architecture audit documents
- **主要修改**：docs/v2/（00-19 + adr/ADR-001~010）；.ai-handoff/ 初版
- **测试**：无（M0 无代码）
- **审核状态**：PASS 方向 / CHANGES_REQUESTED 精度 → 转 M0.1

## 2026-08-09 · M0.1 REVIEW FIX

- **任务**：修复外部审核 14 项 finding + 建立双 Memory + 更新 handoff
- **Commit**：docs: apply M0 external review and bootstrap AI memory（本轮）
- **主要修改**：
  - B~N 14 项修复（见 HANDOFF.md 修复表）：llm 耦合、stop 顺序、Platform 契约、Reverse WS server 所有权、echo 帧关联、有界队列、transport dedup、Guard 范围、Provider 前移 M2、M2 仓储、删消息页验收、阶段激活、Runtime 激活表、Outbound 直连
  - docs/context/CHATGPT_MEMORY.md + AGENT_MEMORY.md（双 Memory 首建）
  - .ai-handoff/ 6 文件更新（含 AGENT_DISCOVERED_DELTA = None beyond corrections）
- **测试**：无（纯文档）；一致性检查 + secret scan 已执行；确认零 V2 代码
- **审核状态**：M0 = PASS（条件），M1 = READY_NOT_STARTED，等待外部审核确认
