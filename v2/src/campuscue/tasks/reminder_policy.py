"""Reminder planning POLICY (M3) — pure, deterministic, testable.

- three default intents per active pending task with deadline:
    day_before   = deadline - 1 day
    hours_before = deadline - 2 hours
    deadline     = at deadline
- MIN_LEAD_SECONDS = 60: candidates closer than 60s to `now` are discarded
- already-past candidates: discarded (never fire immediately, never backfill)
- quiet hours: OVERNIGHT-only wrapping window 23:00 -> 08:00 local (default,
  configurable via start>end); canonical `is_inside_quiet_hours` predicate is
  the single source of truth used by folding, validation and tests
- HARD INVARIANTS (M3.1-B + M3.2-A) for every returned DesiredReminder:
    1. trigger_at <= task.deadline (never after the deadline)
    2. trigger_at NOT inside quiet hours (07:59:59 is still quiet; latest
       allowed pre-quiet moment is 22:59:59 for default 23-08)
    3. trigger_at >= now + min_lead
  Forward folding exceeding the deadline clamps to the latest allowed
  pre-quiet moment of the same local day, else that intent is DISCARDED.
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

    def __post_init__(self) -> None:
        # M3.2-A: OVERNIGHT-ONLY quiet window contract (23->8). The policy only
        # supports wrapping windows where start > end. Same-day / equal / invalid
        # configurations are rejected explicitly — never silently misinterpreted.
        for name, value in (
            ("quiet_start_hour", self.quiet_start_hour),
            ("quiet_end_hour", self.quiet_end_hour),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 23:
                raise ValueError(f"{name} must be an hour 0-23, got {value!r}")
        if not self.quiet_start_hour > self.quiet_end_hour:
            raise ValueError(
                f"quiet hours must be an OVERNIGHT wrapping window "
                f"(quiet_start_hour > quiet_end_hour), got start={self.quiet_start_hour} "
                f"end={self.quiet_end_hour}"
            )


DEFAULT_POLICY = ReminderPolicy()


@dataclass(frozen=True)
class DesiredReminder:
    type: str  # ReminderType value
    trigger_at_utc: datetime  # aware UTC


def is_inside_quiet_hours(local_dt: datetime, policy: ReminderPolicy) -> bool:
    """CANONICAL quiet-hours predicate (M3.2-A). Single source of truth used by
    folding, validation and tests — never duplicated.

    Overnight window [quiet_start_hour, quiet_end_hour): a local datetime is
    inside quiet hours when hour >= start OR hour < end (wrapping window).
    """
    h = local_dt.hour
    return h >= policy.quiet_start_hour or h < policy.quiet_end_hour


def _last_allowed_before_quiet(local_dt: datetime, policy: ReminderPolicy) -> datetime:
    """Deterministic latest allowed moment BEFORE quiet starts on the given
    local day: (quiet_start_hour - 1):59:59. For default 23-08 this is 22:59:59
    — NOT 07:59:59 (07:59:59 is still inside quiet hours)."""
    start = policy.quiet_start_hour
    if start == 0:  # defensive: cannot build hour=-1
        raise ValueError("quiet_start_hour=0 is not an overnight window")
    return local_dt.replace(hour=start - 1, minute=59, second=59, microsecond=0)


def _fold_quiet_hours(local_dt: datetime, policy: ReminderPolicy) -> datetime:
    """Fold a local trigger into the nearest allowed deterministic time.

    If the trigger lands inside quiet hours [start, end):
    - fold FORWARD to end_hour (08:00) of the same local day when that is
      still in the future at decision time; otherwise next day 08:00.
    Uses the canonical is_inside_quiet_hours predicate.
    """
    if not is_inside_quiet_hours(local_dt, policy):
        return local_dt
    # inside quiet hours -> next allowed boundary (end of window)
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

    # 1) quiet-hours folding (local computation, persisted UTC). HARD INVARIANTS
    # (M3.1-B + M3.2-A) for every returned DesiredReminder:
    #   1. trigger_at <= task.deadline  (never notify after the deadline)
    #   2. trigger_at NOT inside quiet hours (07:59:59 is still quiet; the
    #      latest allowed pre-quiet moment is 22:59:59 for default 23-08)
    # When forward folding would exceed the deadline, clamp to the latest
    # allowed pre-quiet moment on the same local day (still < deadline),
    # otherwise DISCARD that intent.
    folded: list[DesiredReminder] = []
    for c in candidates:
        local_t = c.trigger_at_utc.astimezone(tz)
        folded_local = _fold_quiet_hours(local_t, policy)
        if folded_local > local_deadline:
            # fold would exceed deadline -> clamp deterministically to the
            # latest allowed BEFORE quiet starts (e.g. 22:59:59), still before
            # deadline; else discard
            clamped = _last_allowed_before_quiet(local_t, policy)
            folded_local = clamped if clamped < local_deadline else None
        if folded_local is not None:
            folded.append(
                DesiredReminder(type=c.type, trigger_at_utc=folded_local.astimezone(timezone.utc))
            )

    # 2) discard: < MIN_LEAD_SECONDS from now, already past (no backfill), or
    # inside quiet hours (defense in depth — the same canonical predicate)
    lead = timedelta(seconds=policy.min_lead_seconds)
    kept: list[DesiredReminder] = []
    for c in folded:
        # defensive hard invariant (M3.1-B): never after the deadline
        if c.trigger_at_utc > task.deadline:
            continue
        # M3.2-A: never inside quiet hours
        if is_inside_quiet_hours(c.trigger_at_utc.astimezone(tz), policy):
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
