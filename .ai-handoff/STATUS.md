# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M2b.2 REAL ENV ACCEPTANCE**
- 状态：**REAL_ENV_ACCEPTANCE_COMPLETE** — 真实 QQ → NapCat → WS → AI-first pipeline → DeepSeek → SQLite 全链路验证；测试 A-E 全 PASS（hello 共存/明确任务 deadline 精确/普通聊天 skipped/语义重复/重启持久化）；316 tests 全绿；等待外部 M2 最终复核
- **Gate**：M0/M1/M2a/M2b.1 = PASS；**M2b.2 = AWAITING_EXTERNAL_M2_FINAL_REVIEW；M2 FINAL = NOT PASS**
- 验证层级：STATIC ✓ / UNIT ✓ / INTEGRATION ✓ / PACKAGE ISOLATION ✓ / **REAL ENV ✓（M2b.2 新增）**
- REAL ENV 证据：真实群消息全链路（NapCat Framework 小号 bot + DeepSeek json_fallback + SQLite Task）；用户大号受保护未触碰
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M2 最终复核 → M3（Reminder）授权

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
