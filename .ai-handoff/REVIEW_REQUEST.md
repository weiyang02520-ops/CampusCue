# REVIEW_REQUEST.md

> M2a.2 审核请求（提交给外部 ChatGPT）。请基于 GitHub 仓库 `weiyang02520-ops/CampusCue` 审核 Final Foundation Cleanup。

## 请求审核内容（对照 M2a.2 prompt §24 报告项）

1. **canonical secret validation**：openai_compatible 不再有本地 regex；构造 + 运行时都调 validation.py（生产源码恰一条规则）
2. **配置数值持久化前拒绝**：validate_provider_config_numeric（finite/>0/拒 bool/温度≥0）；repository 测试 5 组非法值 + 未持久化证明
3. **request override 校验**：chat() 边界 validate_request_override；8 组非法 override 测试断言**无传输调用**（called==[]）
4. **NaN/Inf 防御**：math.isfinite 在配置/请求真实路径测试（timeout inf/nan、temperature nan/inf）
5. **Clock 所有权**：只有 SystemClock 读墙钟；storage/models.py 源码断言无 datetime.now
6. **ORM 隐藏墙钟 REMOVED**：_utcnow/_aware_utc 删除；created_at/updated_at required（直接 ORM insert 无时间戳 → NOT NULL 失败）
7. **HANDOFF canonical**：单一文档（M2a.2 当前 + 历史指针），无 append 残留
8. **PROJECT_STATE 语义健康**：全重写；blocked/next_gate/verified 无 stale M1.3 字段

## 风险与未验证项（诚实声明）

- REAL PROVIDER：NOT RUN（M2b 真实验收）
- REAL QQ：M1.2 prior verification 保留；无新声明
- 无迁移框架

## Real Verified vs Not

- **CONFIRMED**：203 tests 全绿（含 17 新增 M2a.2）、fresh venv 隔离（FixedClock smoke）、Anti-AstrBot
- **NOT VERIFIED**：真实 Provider 调用

## 视觉审核

无 UI/视觉产出（M6 时提交 `VISUAL REVIEW REQUIRED BY EXTERNAL MODEL`）。
