"""Reminder planning POLICY (M3) — pure, deterministic, testable.

- three default intents per active pending task with deadline:
    day_before   = deadline - 1 day
    hours_before = deadline - 2 hours
    deadline     = at deadline
- MIN_LEAD_SECONDS = 60: candidates closer than 60s to `now` are discarded
- already-past candidates: discarded (never fire immediately, never backfill)
- quiet hours folding: 23:00 -> 08:00 local (configurable); a trigger landing
  inside quiet hours folds FORWARD to 08:00 same day (or next day when the
  fold would itself be past); calculation in supplied timezone, persisted UTC
- HARD INVARIANT (M3.1-B): a reminder is NEVER scheduled after task.deadline.
  If forward folding would exceed the deadline, the trigger clamps to the last
  allowed pre-deadline quiet boundary (quiet_end-1s of the same local day) when
  that is still before the deadline, otherwise that intent is DISCARDED. No
  post-deadline notification is ever emitted to satisfy quiet hours.
- same-minute dedup: if two intents collapse onto the same final minute, keep
  ONE (deterministic precedence: day_before > hours_before > deadline)
- task with deadline=None -> no reminders
- task status pending_confirm / done / dismissed -> no reminders

All inputs/outputs timezone-aware; no hidden wall clock (ADR-010).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from campuscue.storage.enums import ReminderType, TaskStatus
from campuscue.storage.models import Task

MIN_LEAD_SECONDS = 60
QUIET_START_HOUR = 23  # 23:00 local
QUIET_END_HOUR = 8  # 08:00 local


@dataclass(frozen=True)
class ReminderPolicy:
    day_before_offset: timedelta = timedelta(days=1)
    hours_before_offset: timedelta = timedelta(hours=2)
    min_lead_seconds: float = MIN_LEAD_SECONDS
    quiet_start_hour: int = QUIET_START_HOUR
    quiet_end_hour: int = QUIET_END_HOUR


DEFAULT_POLICY = ReminderPolicy()


@dataclass(frozen=True)
class DesiredReminder:
    type: str  # ReminderType value
    trigger_at_utc: datetime  # aware UTC


def _fold_quiet_hours(local_dt: datetime, policy: ReminderPolicy) -> datetime:
    """Fold a local trigger into the nearest allowed deterministic time.

    If the trigger lands inside quiet hours [start_hour, end_hour):
    - fold FORWARD to end_hour (08:00) of the same local day when that is
      still in the future at decision time; otherwise next day 08:00.
    This is deterministic (no wall-clock dependence beyond `local_now`).
    """
    if not (policy.quiet_start_hour <= local_dt.hour or local_dt.hour < policy.quiet_end_hour):
        return local_dt
    # inside quiet hours -> next allowed boundary
    candidate = local_dt.replace(hour=policy.quiet_end_hour, minute=0, second=0, microsecond=0)
    if candidate <= local_dt:
        candidate = candidate + timedelta(days=1)
    return candidate


def _same_minute(a: datetime, b: datetime) -> bool:
    return a.replace(second=0, microsecond=0) == b.replace(second=0, microsecond=0)


def plan_desired_reminders(
    *,
    task: Task,
    now: datetime,
    tz: ZoneInfo,
    policy: ReminderPolicy = DEFAULT_POLICY,
) -> list[DesiredReminder]:
    """Compute the desired reminder intents for one task (pure).

    Returns zero reminders for: deadline=None, non-pending status, all
    candidates discarded (<60s or past). Same-minute collapse keeps one
    with precedence day_before > hours_before > deadline.
    """
    if task.deadline is None:
        return []
    if task.status != TaskStatus.PENDING.value:
        return []
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if task.deadline.tzinfo is None:
        raise ValueError("task.deadline must be timezone-aware")

    local_deadline = task.deadline.astimezone(tz)
    candidates: list[DesiredReminder] = [
        DesiredReminder(
            type=ReminderType.DAY_BEFORE.value,
            trigger_at_utc=(local_deadline - policy.day_before_offset).astimezone(timezone.utc),
        ),
        DesiredReminder(
            type=ReminderType.HOURS_BEFORE.value,
            trigger_at_utc=(local_deadline - policy.hours_before_offset).astimezone(timezone.utc),
        ),
        DesiredReminder(
            type=ReminderType.DEADLINE.value,
            trigger_at_utc=local_deadline.astimezone(timezone.utc),
        ),
    ]

    # 1) quiet-hours folding (local computation, persisted UTC). HARD INVARIANT
    # (M3.1-B): folding must NEVER move a reminder AFTER task.deadline — no
    # notifying after the deadline merely to satisfy quiet hours. When forward
    # folding would exceed the deadline, use a deterministic allowed time
    # BEFORE the deadline (the last quiet-allowed second at quiet_end - 1s of
    # the same local day when still before deadline, else the deadline minute
    # itself is kept only if within quiet hours; otherwise discard).
    folded: list[DesiredReminder] = []
    for c in candidates:
        local_t = c.trigger_at_utc.astimezone(tz)
        folded_local = _fold_quiet_hours(local_t, policy)
        if folded_local > local_deadline:
            # fold would exceed deadline -> clamp deterministically:
            # last allowed pre-deadline quiet boundary (quiet_end-1s of the
            # same local day) when that is still before deadline; else discard
            clamped = local_t.replace(
                hour=policy.quiet_end_hour - 1, minute=59, second=59, microsecond=0
            )
            folded_local = clamped if clamped < local_deadline else None
        if folded_local is not None:
            folded.append(
                DesiredReminder(type=c.type, trigger_at_utc=folded_local.astimezone(timezone.utc))
            )

    # 2) discard: < MIN_LEAD_SECONDS from now, or already past (no backfill)
    lead = timedelta(seconds=policy.min_lead_seconds)
    kept: list[DesiredReminder] = []
    for c in folded:
        # defensive hard invariant (M3.1-B): never after the deadline
        if c.trigger_at_utc > task.deadline:
            continue
        if c.trigger_at_utc < now:
            continue  # past: no backfill
        if c.trigger_at_utc - now < lead:
            continue  # too close: discard
        kept.append(c)

    # 3) same-minute dedup (precedence day_before > hours_before > deadline)
    precedence = {
        ReminderType.DAY_BEFORE.value: 0,
        ReminderType.HOURS_BEFORE.value: 1,
        ReminderType.DEADLINE.value: 2,
    }
    by_minute: dict[datetime, DesiredReminder] = {}
    for c in sorted(kept, key=lambda x: precedence.get(x.type, 9)):
        minute_key = c.trigger_at_utc.replace(second=0, microsecond=0)
        if minute_key not in by_minute:
            by_minute[minute_key] = c
    return [by_minute[k] for k in sorted(by_minute)]
