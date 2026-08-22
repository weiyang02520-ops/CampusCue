# CampusCue M7.3 Bounded Agent Copilot — Implementation Plan

## Scope

Implement the authorized M7.3 boundary on top of the existing M7.2 runtime:

- make Agent writes code-gated behind one in-memory, source-scoped,
  thread-scoped confirmation;
- expose safe, high-level tool activity from actual runtime execution through
  the existing `/api/v1/agent/chat` response;
- add a small confirmation UI without adding an endpoint or database table;
- provide a deterministic local M7-A10 acceptance harness and a documented
  demo package.

Explicit non-goals: durable approval storage, a generic approval framework,
additional Agent tools, new API endpoints, schema migrations, real QQ testing
without a confirmed isolated account/group, and M7.4.

## Design Decisions

1. `ToolDefinition` owns semantic metadata for `mutation` and
   `requires_confirmation`; the registry remains the single classification
   source.
2. `CampusAgentRuntime.chat_with_trace()` returns a bounded per-turn result;
   the existing `chat()` string API remains compatible for QQ handlers and
   older tests.
3. Pending proposals are frozen in memory by thread and source. A confirmed
   proposal executes directly through the existing `ToolRegistry`; the model
   is not called again to regenerate arguments.
4. Grounding uses the existing source-scoped read tools before a proposal.
   Deadline phrases continue through the existing deterministic normalizer.
5. Tool activity is a safe label emitted by actual registry execution or an
   actual code-enforced pending state. Raw arguments, IDs, source text, and
   provider details never leave the runtime.
6. M7-A10 uses the official M7.1 fixture, real SQLite, TaskPipeline,
   TaskService, ReminderService, AgentRuntime, and a deterministic provider;
   it records duration and writes only test/evidence artifacts.

## Test-First Tasks

1. Add focused metadata and runtime tests for proposal, confirmation,
   rejection, ambiguous confirmation, replay, cross-source, restart, and
   activity privacy.
2. Implement the smallest runtime/registry changes until the focused tests
   pass without changing the M4 string-returning contract.
3. Add API/UI assertions for confirmation state and activity rendering.
4. Add the deterministic full-loop harness and demo documentation.
5. Run M7.1/M7.2/M6 regressions, fresh installed-package verification,
   frontend gates, and security/documentation checks.
