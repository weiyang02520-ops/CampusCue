# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M2a.1 FOUNDATION CORRECTNESS FIX**
- 状态：**COMPLETE** — 6 项外部审核修复（test 路径/timeout/枚举/schema 零变更/Clock/secret 早校验）+ get_by_id + 严格解析 + 状态先分类；186 tests 全绿；等待外部复核
- **Gate**：M0/M1/M1.3 = PASS；**M2 = IN_PROGRESS（M2a 完成；M2b NOT_AUTHORIZED）**
- 验证层级：STATIC ✓ / UNIT ✓（70）/ INTEGRATION ✓（17，fake NapCat）/ PACKAGE ISOLATION ✓ / **REAL ENV ✓**
- REAL ENV 证据：私聊+群聊 hello→received:hello（机器侧 action+retcode0 + 用户确认）；非 hello 无回复；重启自动重连；token 握手成功；messagePostFormat=array 兼容
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M2a.1 复核 → M2b 授权

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
