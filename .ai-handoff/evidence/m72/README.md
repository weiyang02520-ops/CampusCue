# CampusCue M7.2 Evidence

This evidence is deterministic, local, and synthetic. It does not use a real
QQ account, real group, real token, or external NapCat instance.

## Scope

- M7.1 external review result: PASS.
- M7.1 cleanup: real `/sources/{id}/test` disconnected coverage and Agent
  activation progress derived from `/agent/threads`.
- M7-A09 implementation: source-scoped OneBot GROUP delivery only.
- M7.3 remains NOT_AUTHORIZED.

## Delivery contract

- `CAMPUSCUE_REMINDER_DELIVERY=noop` is the default and sends nothing.
- `onebot` is a closed, explicit operator opt-in and requires reminders enabled.
- Reminder target is resolved only by `Task.source_id → Source.conversation_id`.
- Only enabled, non-deleted `platform=onebot` GROUP sources are supported.
- Message formatting is deterministic and excludes raw source text, IDs,
  provider/model, confidence, trace IDs, and secrets.
- `fired` means the reminder trigger attempt occurred. Delivery failures are
  classified in the existing safe `Reminder.error` field.
- No automatic retry, delivery table, schema migration, or extra channel.

## Traces

### fake-napcat-success

```text
runtime: CampusRuntime + ReminderScheduler + OneBotAdapter
mode: onebot (explicit opt-in)
source: platform=onebot, conversation_id=24680, enabled=true
task: 高等数学第三章作业, source_id=<canonical source id>
reminder: scheduled → fire()
outbound: send_group_msg, group_id=24680
message: CampusCue 提醒 / 高等数学第三章作业 / 课程：高等数学 / 截止时间：2026-08-28 22:00
fake NapCat action response: status=ok, retcode=0
reminder: fired, error=null
second fire: no outbound action
duplicates: 0
```

### fake-napcat-disconnected

```text
adapter connected: false
outbound actions: 0
reminder: fired
error: delivery:adapter_disconnected
secrets/raw frames: not persisted
```

### fake-napcat-action-failure

```text
adapter connected: true
action response: failure
outbound attempt: 1
reminder: fired
error: delivery:action_failed
raw response/retcode payload: not persisted
```

## Verification commands

- `python -m pytest -q tests/integration/test_m72_onebot_reminder_delivery.py`
- `python -m pytest -q tests/integration/test_m71_first_use_activation.py`
- `npx playwright test tests/e2e/m72-reminder-delivery.spec.ts tests/e2e/m71-first-use-activation.spec.ts`

The real-QQ acceptance path was not run: `REAL QQ E2E = NOT_RUN`.
