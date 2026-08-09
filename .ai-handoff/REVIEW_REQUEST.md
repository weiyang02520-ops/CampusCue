# REVIEW_REQUEST.md

> M0.1 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 直接审核本轮修复。

## 请求审核内容

**本轮新增/修改**：

1. `docs/context/CHATGPT_MEMORY.md` + `AGENT_MEMORY.md` —— 双 Memory 是否满足 high-fidelity recovery（建议对照 M0.1 prompt §P/Q 的 17/18 节逐项核对）
2. 14 项 finding 修复对照（见 HANDOFF.md 修复表）：
   - B：02_V1_AUDIT llm.py 耦合 → NONE/LOW + REWRITE_INTEGRATION
   - C：03/19 stop() 有序 cleanup + Platform 契约修正
   - D/E：04 重写（Reverse WS SERVER + echo correlation + 帧分类）
   - F/G/H：04 有界队列 + transport dedup + Guard 范围
   - I：08/17/10 Provider Foundation 前移 M2
   - J/K：06/09/17 M2 仓储 + 删消息页验收
   - L/M/N：10 阶段激活 + 07 激活表 + 05 Outbound 直连

## 需要确认的结论

1. 所有 finding 是否修复正确（对照原文语义，非表面替换）
2. 双 Memory 是否遗漏 P/Q 要求的任何节
3. Milestone dependency（Provider→M2、Reminder→M3、Realtime→M5）是否全局一致（AD 一致性检查已执行，请复核）
4. Memory provenance 标签使用是否正确（无 INFERRED 冒充 CONFIRMED）

## 风险与未验证项（诚实声明）

- M0.1 零代码、零测试运行
- 双 Memory 为首次建立，恢复效果需外部 ChatGPT 实际"失忆读取"验证
- 14 项修复为文档层，未影响任何代码（无代码）

## Real Verified vs Not

- **CONFIRMED**：源码事实引用（llm.py 直连 Ark 无 astrbot 依赖、core_lifecycle.stop() 实际顺序、Platform 基类方法清单——均已在 M0 研究时读码）
- **NOT VERIFIED**：双 Memory 恢复效果（需外部模型实测）、M1 设计（文档层）

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
