# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M2b.1.1 REAL-GATE HARDENING**
- 状态：**COMPLETE** — 外部 M2b.1 复核 PASS_WITH_FIXES 的 8 项 fix 全部落地（缺 secret fail-before-transport / provider-model 审计 / model_said_none reason / fallback 分类 / context resize / 显式年份 / test DB 隔离 / 所有权清理）+ dedup key + injection 防御；302 tests 全绿；等待外部 M2b.1.1 最终复核
- **Gate**：M0/M1/M2a = PASS；M2b.1 = AWAITING_EXTERNAL_FINAL_REVIEW；**M2b.2 = NOT_AUTHORIZED；M2 FINAL = NOT PASS**
- 验证层级：STATIC ✓ / UNIT ✓（+38 断言组）/ INTEGRATION ✓（fake NapCat）/ PACKAGE ISOLATION ✓（.venv-m2iso）/ **REAL ENV ✓（仅 M1.2 保留，非本轮）**
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M2b.1.1 最终复核 → M2b.2 授权

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
