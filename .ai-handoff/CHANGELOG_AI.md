# CHANGELOG_AI.md

> AI 变更日志（供后续模型追历史，不依赖聊天记录）。

## 2026-08-09 · M0

- **任务**：M0 Architecture / Audit（研究 AstrBot 固定基准 + 审计 V1 + V2 设计文档）
- **Commit**：docs: M0 architecture audit documents（待提交）
- **主要修改**：
  - 新增 `docs/v2/`（00-19 共 20 份 + adr/ADR-001~010）
  - 新增 `.ai-handoff/`（PROJECT_STATE / STATUS / HANDOFF / REVIEW_REQUEST / NEXT_TASKS / DECISIONS / CHANGELOG_AI）
- **研究**：AstrBot commit 30e20318c 9 条链路；V1 commit db35d77 全量审计
- **测试**：无（M0 无代码）
- **审核状态**：AWAITING_EXTERNAL_REVIEW
- **备注**：审计新发现 B12（时区硬编码）、B13（LLM 测试缺口）已入 13_BUG_LESSONS.md
