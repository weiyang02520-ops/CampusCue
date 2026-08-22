# STATUS.md

> 当前状态摘要。详细内容见 canonical HANDOFF.md 与 PROJECT_STATE.md。

- 阶段：**M7.2 ONEBOT REMINDER DELIVERY IMPLEMENTATION COMPLETE（AWAITING EXTERNAL REVIEW）**
- **M4 FINAL = PASS**
- **M5 FINAL = PASS**（External ChatGPT）
- **M6 = CHANGES_REQUESTED（已按外部审核修复）**
- **M6.1 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**
- **M6.2 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**
- **M6.2.1 = IMPLEMENTATION_COMPLETE_AWAITING_VISUAL_REVIEW**
- **M6.3 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.4 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5 = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5.1 GLASS = EXTERNAL_VISUAL_REVIEW_PASS**（方向与材质成立）
- **M6.5.2 GLASS = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5.3 DARK STAGE 1 = PASS**；**M6.5.3 DARK = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **M6.5.4 NEUMORPHISM = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_VISUAL_REVIEW**
- **NEUMORPHISM MATERIAL = PASS**；**M6.5.4.1 THEME UX = PASS**
- **GLASS FINAL = PASS**；**DARK FINAL = PASS**；**NEUMORPHISM FINAL = PASS**
- **M6 FINAL = PASS**（CampusCue WebUI completed）
- **M7 ROADMAP DESIGN = PASS**；**M7.0 PRODUCT CONTRACT = PASS**；**M7.1 FIRST-USE ACTIVATION = PASS**；**M7.2 ONEBOT REMINDER DELIVERY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**；**M7.3 = NOT_AUTHORIZED**
- M5 REST/SSE：PASS（Tasks/Sources/Messages/Reminders/Providers/Agent/Settings/System/Backup/Restore/Import/Export/Auth/Health）
- M7.2 implementation：OneBot GROUP delivery is explicit opt-in; default Noop; deterministic message, safe delivery error taxonomy, duplicate fire guard, startup/shutdown ordering, and fake NapCat evidence are complete. M7.1 external review = PASS; real QQ E2E = NOT_RUN.
- Schema：v3（settings + sources.deleted_at + indexes；migration atomic）
- Full V2：**488 passed**（fresh `.venv-m511fresh` non-editable）；M5/M5.1/M5.1.1 focused **24 passed**；M5.1.1 new **1 passed**
- compileall PASS；Anti-AstrBot PASS；uvicorn local HTTP smoke PASS
- Findings A-D、Realtime event completeness、actual SSE lifecycle、occupied-port rollback：PASS（local evidence）
- Known limitation：M4 source_message_id uniqueness remains；M3 cross-repository atomicity open risk；SSE no-replay。
- M6.2 WebUI：保留八页面与 M5 contract；tokens/surface hierarchy/accent/status/deadline/brand/micro-motion polish；light `.ai-handoff/visual/m62/` + dark `.ai-handoff/visual/m62-dark/`；axe 0；Playwright full 12 passed；等待外部视觉审核。
- M6.2.1：Home 动态日期/时区、完成/忽略分离、移动端 More bottom sheet、canonical priority、共享 labels、theme icon/topbar cleanup；focused Playwright 12 passed；light `.ai-handoff/visual/m621/` + dark `.ai-handoff/visual/m621-dark/`；等待外部视觉审核。
- M6.3：Cue Line + Cue Dot、page identity、section tint、structured empty states、Tasks/Agent/Calendar/Home 核心页和其余四页视觉收口；typecheck/build/unit/Axe/focused E2E/individual real integration PASS；light `.ai-handoff/visual/m63/` + dark `.ai-handoff/visual/m63-dark/`；等待外部视觉审核。
- M6.4：progressive disclosure / three-level information hierarchy；Tasks/Agent/Messages primary pass，Calendar/Connections/Providers/Settings context and advanced cleanup；fresh V2 488 passed；focused Playwright 16 passed；real integration 2 passed；light `.ai-handoff/visual/m64/` + dark `.ai-handoff/visual/m64-dark/`；等待外部视觉审核。
- M6.5：editorial page composition、surface hierarchy、局部玻璃拟态（含实色回退）、明暗与响应式收口；typecheck/build/unit/axe/focused E2E/real integration PASS；light `.ai-handoff/visual/m65/` + dark `.ai-handoff/visual/m65-dark/`；等待外部视觉审核。
- M6.5.1 Glass（historical）：只返工 App Shell/Home/Tasks/Agent；Atmospheric Canvas + `glass-subtle/panel/raised/floating` + Backdrop/Tint/Blur/Edge/Shadow/Contrast/Fallback；Glass material test 1 passed；证据 `.ai-handoff/visual/m651/glass/`；方向已通过外部视觉审核。
- M6.5.2 Glass：降低 backdrop、统一 Base/Primary/Context/Raised/Floating semantic tiers；Home Today 去嵌套白卡；Tasks toolbar/context/rows 与本地化日期；Agent utility/prompt/composer/mobile refinement；Stage 1 证据 `.ai-handoff/visual/m652/glass/`；等待外部 Glass 视觉审核。
- M6.5.3 Dark：Stage 1 独立 solid-surface Dark UI 覆盖 App Shell/Home/Tasks/Agent/Settings selector；7 张 evidence 位于 `.ai-handoff/visual/m653/dark/`；Dark focused 2、M6 focused 16、Glass focused 2、real integration 2、Axe/overflow/console/theme/mobile composer PASS；等待外部 Dark 视觉审核。基线 `m6.5.2-glass-baseline` 已推送。
- M6.5.3 Dark Stage 2：完成 Calendar/Messages/Connections/Providers/Settings、Dialog/Bottom Sheet/Toast/Empty/Loading/Offline/Reconnecting 与 1440/1024/390 responsive evidence；新增 `.ai-handoff/visual/m653-stage2/dark/` 和 `.ai-handoff/visual/m653-stage2/compare/`，语义 Theme Selector + `system` media sync；Stage 1 = PASS，Dark implementation complete awaiting external visual review。
