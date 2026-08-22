# CampusCue M7 Roadmap

> 状态：**M7.0 PRODUCT CONTRACT = PASS；M7.1 PASS；M7.2 ONEBOT REMINDER DELIVERY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW**
>
> M7.1 已通过外部审核；M7.2 已完成实现并等待外部审核；M7.3 仍为 **NOT_AUTHORIZED**。
> 本文是 M7 的范围设计；Product Contract 已收敛到 [`M7_PRODUCT_CONTRACT.md`](M7_PRODUCT_CONTRACT.md)。M7.1 已按窄范围授权并完成实现，等待外部审核；M7.2/M7.3 仍为 **NOT_AUTHORIZED**。

## 1. Current State

### 1.1 Project truth

- M0-M5：PASS；M6 WebUI：PASS。
- M6 final review record commit：`84ec82db6905c088339b13cc64b0b888c1c39ab4`。
- Git remote 在本轮开始时核验为 `HEAD == origin/main == 84ec82d`，working tree clean。
- CampusCue V2 是零 AstrBot 依赖的校园事务 AI Agent 平台；DB 是业务事实源，SSE 只是通知，TaskService 是任务写入入口。
- 当前产品页面：Home、Tasks、Messages、Calendar、Agent、Connections、Providers、Settings。
- 当前后端能力：OneBot/NapCat 来源、AI-first extraction、TaskService、ReminderService、Provider Manager、bounded Agent tool loop、REST、SSE、Backup/Restore/Import/Export。
- 已有真实证据：DeepSeek Provider Tool Call、真实 QQ Agent E2E、M5 REST/SSE、fresh installed-package V2 488 tests passed、M6 三主题 WebUI final review PASS。

### 1.2 Existing boundary

Current Agent is deliberately small:

- source-scoped context；
- bounded in-memory conversations；
- maximum tool-loop steps；
- task/reminder/source tools；
- all mutations go through TaskService；
- no long-term memory、SubAgent、MCP、Skills、Computer Use 或 streaming provider chain。

Current reminder facts are persisted and scheduler jobs are derived, but the runtime is wired to `NoopDelivery`. This is a product gap, not permission to redesign the reminder subsystem during roadmap design。

### 1.3 Documentation drift to resolve later

`v2/README.md` still contains the historical “M6 WebUI not yet implemented” line, while the canonical handoff and Git state record M6 as PASS. This roadmap treats the handoff/current Git state as authoritative and records README alignment as a small documentation task, not as a product feature。

## 2. Product Vision

CampusCue should make a student’s scattered campus messages actionable without turning into a generic chatbot:

```text
message source
  → understand
  → extract task with evidence
  → manage task
  → remind at the right time
  → ask bounded Agent
  → complete the task
```

The M7 product promise is narrower than “an intelligent campus operating system”:

> Within five minutes of first use, a student can connect one source, see one trustworthy task, ask the Agent about it, and receive a useful, source-grounded answer.

M7 success is measured by completion of this loop, not by the number of tools, integrations, tables, or visual surfaces added。

## 3. Problems

This section intentionally states problems and impact before proposing solutions。

| Problem | Impact | Priority |
|---|---|---:|
| First-use path is distributed across Connections, Messages, Tasks and Agent instead of feeling like one guided product loop。 | A new user may not know which source to connect, how a message becomes a task, or where to ask for help。 | P0 |
| Sources, extraction evidence, confidence and task provenance are technically present but not yet a single trust story。 | Users may see a task without understanding why it exists or whether they should confirm it。 | P0 |
| Reminder scheduling exists, but user-visible delivery is still a NoopDelivery boundary。 | The product can plan a reminder without proving that the student actually receives help at the right time。 | P0 |
| Agent works against real source-scoped tasks, but its boundary is not yet expressed as a product contract。 | Users can overestimate what it knows; unsupported questions and ambiguous mutations can become trust failures。 | P1 |
| Agent conversations are bounded in memory and disappear on restart。 | Continuity is limited, but adding durable memory without a clear use case would create privacy and scope risk。 | P1 |
| One source message can create at most one Task because of the existing `(source_id, source_message_id)` uniqueness contract。 | Compound announcements cannot be split into multiple tasks without an explicit product rule。 | P1, bounded |
| Task/Reminder cross-repository atomicity remains an open design risk。 | A rare failure can leave task and reminder facts temporarily out of sync, although startup resync provides recovery。 | P1, correctness |
| SSE has no replay and clients must REST refresh after reconnect。 | A disconnected client can miss notifications unless the canonical refresh path remains reliable。 | P1, correctness |
| Campus data integration is not a single feature; courses, exams, notices and calendars have different ownership and freshness rules。 | A broad connector initiative could consume M7 without proving the core task loop。 | P2 |
| The current README and some historical handoff sections describe pre-M6 states。 | External reviewers and future agents can infer the wrong current scope。 | P1, documentation |

## 4. Candidate Directions

### Direction A — Agent Intelligence

**Value:** High if it helps users decide what to do next from canonical tasks; low if it becomes a general-purpose chat surface。

**Difficulty:** High. Planning, multi-step reasoning, tool orchestration and memory each introduce failure modes, evaluation cost and privacy questions。

**Risk:** Scope explosion, tool loops that are hard to explain, accidental access across source boundaries, and “memory” that outlives user intent。

**M7 decision:** **Enter in a bounded form only.** M7 may define a task copilot contract with explicit tool scope, confirmation rules, step limits and no durable long-term memory. Generic planning, SubAgents, MCP, Skills and autonomous background work are out。

### Direction B — Task Intelligence

**Value:** Highest alignment with CampusCue. Better extraction confidence, evidence, deadline interpretation, review and reminder follow-through directly improve the core loop。

**Difficulty:** Medium to high. Time semantics, uncertainty and notification delivery need deterministic behavior and real acceptance data。

**Risk:** Silent model decisions can damage trust; schema changes can become premature; reminder delivery can become platform-specific too early。

**M7 decision:** **Enter as the primary product direction.** Reuse existing fields and TaskService first. New schema is not assumed; it requires a demonstrated acceptance gap and a separate design decision。

### Direction C — Campus Data Integration

**Value:** Potentially high for course/exam context and broader campus usefulness。

**Difficulty:** Very high. Every registrar, LMS, notification channel or calendar has different authentication, format, freshness and permission behavior。

**Risk:** Connector maintenance dominates the product, secrets/privacy become central, and the core message-to-task loop remains unproven。

**M7 decision:** **Do not enter as a broad integration program.** Keep a documented adapter boundary and consider at most one narrow, user-owned import/fixture path after the M7 MVP proves value。

### Direction D — Productization

**Value:** Immediate. Onboarding, demoability, deployment clarity and documentation turn existing engineering into a product someone can understand and try。

**Difficulty:** Medium. The risk is mainly prioritization and keeping the first-run path deterministic。

**Risk:** Cosmetic polish can disguise an incomplete loop; deployment work can outrun user value。

**M7 decision:** **Enter and pair with Task Intelligence.** Productization must be measured by first-use completion and a repeatable demo, not by a larger settings surface。

### Direction E — Collaboration

**Value:** Real for team/project use, but not necessary to prove the first CampusCue product promise。

**Difficulty:** Very high. Requires identity, ownership, permissions, conflict handling, auditability and shared reminder semantics。

**Risk:** It changes the single-user/source-scoped mental model and creates a second product before the first one is complete。

**M7 decision:** **Defer.** No groups, shared tasks, team roles or multi-user authorization in M7。

## 5. Prioritization

| Direction | Product value | Urgency | Complexity | Risk | M7 treatment |
|---|---:|---:|---:|---:|---|
| Productization | 5 | 5 | 3 | 2 | Core |
| Task Intelligence | 5 | 5 | 4 | 3 | Core |
| Bounded Agent copilot | 4 | 4 | 4 | 4 | Thin slice |
| Campus Data Integration | 4 | 2 | 5 | 5 | Defer |
| Collaboration | 3 | 1 | 5 | 5 | Defer |

### Recommended M7 MVP

The M7 MVP is one narrow vertical slice:

1. guided source connection and connection validation；
2. one real message becoming a task with visible provenance/confidence；
3. explicit confirmation or correction for uncertainty；
4. one user-visible reminder path or a clearly testable delivery boundary；
5. one source-scoped Agent question answered from canonical task data；
6. a deterministic demo/onboarding path that completes this sequence in five minutes。

M7 MVP is **not** an Agent platform, a campus integration platform, or a collaboration product。

## 6. M7 Milestones

### M7.0 — Product Contract and Scope Lock

**Goal:** Freeze the narrow M7 promise, vocabulary, evidence plan and non-goals before implementation。

**Scope:**

- first-use journey and success events；
- source → extraction → task → reminder → Agent traceability；
- bounded Agent boundary and confirmation rules；
- evaluation fixtures and acceptance scenarios；
- deployment/demo assumptions；
- documentation alignment for current M6 state。

**Non-goals:**

- no source connector implementation；
- no Agent behavior expansion；
- no Schema/API change；
- no UI redesign；
- no M7 implementation authorization beyond the separately approved slice。

**Acceptance:**

- one-page product contract is approved externally；
- five-minute journey has observable start/end criteria；
- every proposed M7 change maps to a named acceptance scenario；
- deferred directions and forbidden scope are recorded；
- no open item is accepted merely because it “looks advanced”。

### M7.1 — First-use Activation

**Goal:** Make the existing source, task and Agent capabilities discoverable as one successful first-use path。

**Scope:**

- one supported source setup path；
- connection test and actionable failure state；
- deterministic first message/task evidence；
- clear source scope and provenance；
- first Agent prompt grounded in the created task；
- instrumentation or evidence sufficient to measure the five-minute journey。

**Non-goals:**

- no multi-platform connector program；
- no account system；
- no collaboration；
- no broad UI restyling；
- no long-term Agent memory。

**Acceptance:**

- a new test user can connect one source, see a task, ask one Agent question and receive a source-grounded answer within five minutes；
- connection failure identifies the next action without exposing secrets；
- task displays source reference and confidence/confirmation state；
- Agent cannot answer from an unselected source；
- the flow works with the deterministic local fixture and one supported real-source path；
- M0-M6 regression gates remain green。

### M7.2 — Trustworthy Task Follow-through

**Goal:** Close the gap between “a task was extracted” and “the user can safely act on it”。

**Scope:**

- explainable extraction confidence and review/confirm behavior；
- deadline/priority/category presentation based on existing canonical fields；
- reminder status and one user-visible delivery path；
- clear failure/retry semantics for provider and delivery errors；
- evidence that task mutation and reminder planning stay idempotent。

**Non-goals:**

- no autonomous priority decisions without user-visible rationale；
- no universal notification matrix；
- no schema migration by default；
- no redesign of ReminderService or cross-repository transaction architecture；
- no compound-task splitting until a separate product rule is approved。

**Acceptance:**

- uncertain extraction is visibly reviewable and never silently presented as certain；
- a changed/cleared deadline produces the expected reminder behavior or a precise actionable error；
- one reminder can be observed end to end through the selected delivery boundary；
- duplicate extraction and duplicate reminder planning remain safe；
- task provenance remains available after mutation；
- reminder/task inconsistency is either prevented in the approved path or surfaced and recovered by resync。

### M7.3 — Bounded Agent Copilot and Demonstration Package

**Goal:** Make the Agent a trustworthy task copilot and package the complete loop for demo, deployment and review。

**Scope:**

- explicit Agent capability contract and user-facing boundary；
- read-first task questions；
- bounded mutations requiring confirmation where ambiguity exists；
- tool activity/result trace suitable for debugging and demo；
- repeatable local demo dataset and deployment/onboarding documentation；
- one happy-path demo and defined failure-path demo。

**Non-goals:**

- no general web research；
- no SubAgent/Handoff/MCP/Skills/Computer Use；
- no autonomous background planning；
- no durable memory unless M7.0 proves a narrowly scoped, privacy-reviewed need；
- no collaboration or shared task permissions。

**Acceptance:**

- Agent answers task/date/reminder questions from canonical data and identifies its source scope；
- Agent uses tools for data access/mutation and does not invent task facts；
- ambiguous create/update/complete actions request confirmation；
- tool loop remains bounded and reports understandable failure；
- clean install can run the documented demo without AstrBot or real secrets in the repository；
- an external reviewer can reproduce the five-minute flow from the documentation。

## 7. Non Goals

The following are explicitly outside M7:

- rewriting the M0-M6 architecture；
- copying AstrBot runtime, plugin behavior or protocol surface；
- a universal Agent or autonomous “do everything” assistant；
- long-term memory, vector RAG or campus-wide knowledge graph；
- broad course/LMS/exam/calendar connector coverage；
- collaboration, groups, shared tasks, roles and multi-user permissions；
- changing backend theme semantics or continuing M6 visual iteration；
- changing Schema/API merely to make the roadmap look complete；
- adding features without a measurable first-use or follow-through acceptance criterion。

## 8. Acceptance Criteria

### Product

- Five-minute first-use journey passes with a new test user and deterministic fixture。
- The user can identify the source, task, deadline, confidence and next action。
- Every extracted task has understandable provenance；uncertain facts require review。
- The product demonstrates at least one reminder follow-through path, not only a scheduled job。

### Agent boundary

**The Agent knows:** selected source scope, canonical tasks, task status/category/course/deadline/priority, reminder facts, current configured timezone and supported source status。

**The Agent does not know:** unselected sources, arbitrary campus data, full historical chat, secrets, private provider values, unsupported web content or durable personal memory unless separately approved。

**The Agent calls tools when:** it must read canonical data, create/update/complete/dismiss a task, inspect reminders or identify the current source。

**The Agent answers directly when:** explaining its capabilities, asking for missing information, clarifying ambiguity, or summarizing already-returned tool results。

**The Agent must ask for confirmation when:** a mutation is ambiguous, affects a deadline/status, or could surprise the user。It must never claim a tool result it did not receive。

### Technical and operational

- M0-M6 tests and fresh-package verification remain green。
- Anti-AstrBot, secret/PII scan and `git diff --check` remain green。
- No new API or Schema is accepted without a written contract, migration/rollback plan and a failing acceptance gap that requires it。
- Source scope isolation, deduplication, reminder idempotency and provider error taxonomy remain covered。
- SSE remains notification-only; reconnect behavior continues to REST-refresh canonical state。
- Demo documentation is reproducible from a clean install and contains no real IDs, secrets or private paths。

## 9. Data Model and Technical Debt Impact

### Data model impact

| Area | M7 MVP position |
|---|---|
| Task | Reuse existing title/description/category/course/deadline/status/priority/confidence/source provenance。No new field assumed。 |
| Source | Reuse enabled/auto_extract/context_window/privacy policy and existing connection identity。No multi-user ownership field。 |
| Message / Extraction | Keep the current extraction projection and privacy rule；do not introduce full chat history storage。 |
| Reminder | Reuse persisted reminder facts and derived scheduler jobs。A delivery record/table requires a separate design only if the selected delivery path cannot be made observable otherwise。 |
| Agent Context | Keep source-scoped bounded in-memory context for MVP。No long-term memory persistence。 |

### Technical debt decisions

- **M3 cross-repository atomicity:** keep the existing startup resync safety net for M7 MVP; address only if the chosen user-visible delivery path exposes a reproducible inconsistency。 Do not redesign preemptively。
- **M4 source-message uniqueness:** keep as a documented first-version constraint; do not split compound announcements until product semantics and dedup rules are approved。
- **SSE no replay:** keep notification-only semantics; test reconnect REST refresh in the first-use/demo flow。 Replay is not an M7 goal。
- **README drift:** align historical M6 status in a documentation-only cleanup before external M7 implementation review。

## 10. Risks and Gates

| Risk | Guardrail |
|---|---|
| M7 becomes another visual/feature expansion | Every change must map to the five-minute loop or task follow-through acceptance。 |
| Agent scope expands into a platform | Keep explicit tool allowlist, source scope, step limit and confirmation policy。 |
| Provider output is unreliable | Use deterministic fixtures, typed extraction, explainable uncertainty and provider error taxonomy。 |
| Reminder delivery becomes platform sprawl | Prove one delivery boundary first；defer notification matrix。 |
| Schema churn hides product uncertainty | No migration without a demonstrated acceptance gap and rollback plan。 |
| Privacy boundary weakens through memory/integration | No durable memory or broad campus data by default；keep secrets out of logs and evidence。 |
| Historical documents contradict current state | Treat canonical handoff/Git as truth and perform a docs alignment pass。 |

### Authorization gate

This roadmap is complete for external review only；M7.1 implementation is separately gated below。

- `M6 FINAL = PASS`
- `M7 ROADMAP DESIGN = PASS`
- `M7.0 PRODUCT CONTRACT = PASS`
- `M7.1 FIRST-USE ACTIVATION = PASS`
- `M7.2 ONEBOT REMINDER DELIVERY = IMPLEMENTATION_COMPLETE_AWAITING_EXTERNAL_REVIEW`
- `M7.3 = NOT_AUTHORIZED`

M7.1/M7.2 implementation mapping and evidence are in [`M7_PRODUCT_CONTRACT.md`](M7_PRODUCT_CONTRACT.md), `.ai-handoff/evidence/m71/` and `.ai-handoff/evidence/m72/`. No full M7 or five-minute Step 0–16 completion is claimed。
