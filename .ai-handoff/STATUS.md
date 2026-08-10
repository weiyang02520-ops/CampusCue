# STATUS.md

> 当前状态摘要（checkpoint 时自动刷新）。实时信息（HEAD/visibility）由脚本获取，不手写。

- 阶段：**M1.2 REAL ENVIRONMENT VERIFICATION**
- 状态：**M1 = PASS（REAL ENV VERIFIED 2026-08-10）** — NapCat v4.18.18 + 真实 QQ 验证完成；等待外部 M1 最终审核
- 验证层级：STATIC ✓ / UNIT ✓（70）/ INTEGRATION ✓（17，fake NapCat）/ PACKAGE ISOLATION ✓ / **REAL ENV ✓**
- REAL ENV 证据：私聊+群聊 hello→received:hello（机器侧 action+retcode0 + 用户确认）；非 hello 无回复；重启自动重连；token 握手成功；messagePostFormat=array 兼容
- 已知 Bug Inventory：docs/v2/13_BUG_LESSONS.md（B01-B13）
- 下一步：外部 M1 最终审核 → M2

（本文件由 checkpoint 流程生成/刷新，详细见 HANDOFF.md 与 PROJECT_STATE.md）
