# M7.2 OneBot Reminder Delivery Design

## Scope

Implement the first real external delivery boundary for CampusCue reminders,
limited to enabled OneBot group sources. Keep the Reminder row as the
canonical fact, reuse the existing `OutgoingMessage` and `OneBotAdapter.send()`
boundary, and keep external delivery opt-in with a closed `noop|onebot` mode.

## Source-truth audit

| Contract item | Actual support | Reuse / action |
|---|---|---|
| Source target facts | `Source.platform`, `conversation_id`, `enabled`, `deleted_at` | Resolve from `Task.source_id`; fail closed |
| Group-only source contract | automatic extraction policy accepts `GROUP` | Delivery accepts OneBot group targets only |
| Reminder canonical fact | `Reminder.status`, `last_run`, `error` | Preserve; no schema change |
| Scheduler | `ReminderScheduler` derives jobs from facts | Install delivery before start |
| Outbound boundary | `OutgoingMessage` + `OneBotAdapter.send` | New delivery adapter only formats and resolves target |
| Connection test | existing `/sources/{id}/test` | Add real disconnected-path regression |
| Agent activation | existing `/agent/threads` | Derive ActivationGuide fourth step from active thread |

## Implementation shape

- Add `ReminderConfig.delivery_mode`, loaded from `CAMPUSCUE_REMINDER_DELIVERY`.
- Keep `noop` as the default; only `onebot` installs `OneBotReminderDelivery`.
- Add a small delivery module that resolves `task.source_id`, validates the
  source, formats deterministic privacy-safe text, and calls the adapter.
- Harden `ReminderService.fire()` with an in-process claim guard and safe
  classified failure persistence. A second sequential/concurrent fire cannot
  send twice.
- Start the scheduler only after adapter start and delivery installation.
- Stop scheduler and wait for reminder delivery before stopping the adapter.
- Keep Reminder API unchanged; existing `error` is the failure projection.

## Failure semantics

Every attempt claims the scheduled fact once. A suppressed target or delivery
failure becomes `fired` with a safe `delivery:*` error. Success is `fired` with
no error. No automatic retry is introduced. Task completion/dismissal and
missing, disabled, deleted, non-OneBot, non-group, or source-less targets do
not send.

## Test-first scenarios

- M7.1 cleanup: activation AI step follows a real thread; A02 calls the real
  source connection test for a disconnected adapter.
- M7-A09 success: real adapter + fake NapCat observes exactly one deterministic
  `send_group_msg` action with the source conversation id.
- M7-A09 failure: disconnected and action-failure paths persist safe errors.
- Wrong/missing source, disabled/deleted/non-OneBot source, completed task:
  zero outbound actions.
- Explicit `onebot` opt-in sends; default `noop` does not.
- Runtime startup has no scheduler-before-delivery window; shutdown waits for
  in-flight delivery before adapter close.

## Non-goals

No schema migration, new API endpoint, retry queue, delivery table, private
message reminder, additional notification channel, real QQ acceptance, Agent
memory/planning, or M6 visual redesign.
