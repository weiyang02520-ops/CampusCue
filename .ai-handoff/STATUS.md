# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M3.1 REMINDER HARDENING**
- 状态：**HARDENING_COMPLETE** — 外部 PASS_WITH_FIXES 的 6 项修复全部落地（config 接线/post-deadline 禁/resync 真重建/迁移验证/约束对齐/默认投递）；354 tests 全绿；等待外部 M3 最终复核
- **Gate**：M0-M2 = FINAL PASS；**M3 = AWAITING_EXTERNAL_REVIEW；M3 FINAL = NOT YET DECLARED；M4+ = NOT_AUTHORIZED**
- 验证层级：STATIC ✓ / UNIT ✓（+38）/ INTEGRATION ✓ / PACKAGE ISOLATION ✓（.venv-m2iso + apscheduler）/ **LOCAL REAL SCHEDULER ✓** / REAL ENV（M2b.2 保留，M3 无 QQ）
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M3 最终复核 → M3 FINAL PASS → M4 授权

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
