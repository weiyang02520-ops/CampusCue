# ADR-011：V2 源码与 Legacy V1 物理隔离

- **Status**：Accepted（M1）
- **Date**：2026-08-09
- **Context**：当前 Git 仓库同时保留 Legacy CampusCue V1（`campuscue/`、`astrbot/`、`dashboard/`）与 V2 docs。若把 V2 源码混入现有 `campuscue/` package，会重新产生 V1/V2 import ambiguity、隐式 AstrBot coupling、测试路径污染与未来迁移困难。
- **Decision**：CampusCue V2 implementation 位于仓库内**独立 V2 implementation root `v2/`**（`v2/src/campuscue/`）。V2 package 必须可独立安装/测试，不依赖根目录 V1 `campuscue/` package、AstrBot runtime 或 AstrBot source。Legacy V1 保持冻结（仅 docs/context、docs/v2、.ai-handoff 等正式文档同步除外）。
- **Alternatives**：V2 写进现有 `campuscue/`（拒绝：import 歧义 + 隐性 AstrBot 耦合）；另开新仓库（拒绝：丢失统一历史与文档链；M0 已定共享仓库）。
- **Reason**：物理隔离是 Python package 级证明 V2 独立性的最可靠方式（import 时不可能碰到 Legacy/AstrBot）；同时保留 V1 作 reference。
- **Consequences**：V2 有自己的 pyproject/依赖/测试路径；V1 不再演进；未来 V1 退役时删除根目录三个 package 不影响 V2。
