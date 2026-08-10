# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M2b.1 TASK EXTRACTION PIPELINE**
- 状态：**COMPLETE** — L0-L7 管道 + TaskService + Mock Provider 全链路 + 并发去重；256 tests 全绿；等待外部 M2b.1 复核
- **Gate**：M2a = PASS；M2b = IN_PROGRESS（M2b.1 完成；M2b.2 NOT_AUTHORIZED）
- **Gate**：M0/M1/M1.3 = PASS；**M2 = IN_PROGRESS（M2a 完成；M2b NOT_AUTHORIZED）**
- 验证层级：STATIC ✓ / UNIT ✓（70）/ INTEGRATION ✓（17，fake NapCat）/ PACKAGE ISOLATION ✓ / **REAL ENV ✓**
- REAL ENV 证据：私聊+群聊 hello→received:hello（机器侧 action+retcode0 + 用户确认）；非 hello 无回复；重启自动重连；token 握手成功；messagePostFormat=array 兼容
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M2b.1 复核 → M2b.2 授权

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
