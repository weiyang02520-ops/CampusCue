# CampusCue M7 Demo Script

The story is one bounded loop: a campus message becomes a grounded task, the
Agent explains it from canonical data, and a write waits for explicit user
confirmation.

1. Minute 1 — show a connected source and its connection state.
2. Minute 2 — send the official message: “高等数学第三章作业请于 2026 年 8 月 28 日 22:00 前提交。” Show extraction, provenance, confidence, task, and reminder.
3. Minute 3 — ask the Agent about this week’s tasks. Point to the high-level activity “已查询当前来源的任务” and the grounded answer.
4. Minute 4 — ask to move the deadline. Show the old value, proposed new value, and the `确认` / `取消` actions. The database is unchanged before confirmation.
5. Minute 5 — confirm once. Show the TaskService result, reminder re-plan, and final task state.

## Failure beats

- NapCat disconnected: show the connection self-test failure, then show a
  reminder safe error and the next step (“检查 QQ 连接”). Do not claim QQ
  delivery.
- Uncertain extraction: show a task with `pending_confirm` and ask the user to
  clarify the missing deadline; do not invent a date.

The local deterministic harness follows the same sequence in under five
minutes without a real provider key or real QQ message.
