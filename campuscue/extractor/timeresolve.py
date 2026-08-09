"""L3: turn a Chinese time phrase into an absolute instant, in code.

Why not let the model do it
---------------------------
"下周二" means nothing without knowing what day the message was sent. Models do
this arithmetic in their heads and get it wrong in ways nobody can audit -- and a
deadline that is quietly one week off is worse than no deadline at all. So L2 is
instructed to copy the phrase verbatim and this module resolves it against the
message's own timestamp.

The two conventions that matter
-------------------------------
"周五晚上12点" is the ambiguous one every student writes. Midnight belongs to no
day: "Friday midnight" could be the instant Friday begins or the instant it ends.
In Chinese campus usage "周五晚上12点前提交" always means the end of Friday, so
``晚上12点`` resolves to Friday 23:59 rather than Friday 00:00. Erring the other
way would move every such deadline a full day earlier and make the reminder fire
before the work was even assigned.

A bare date with no clock time ("8月10日截止") resolves to 23:59 of that day and
is flagged ``is_explicit=False``, so the UI can show that the time-of-day was
inferred rather than stated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CAMPUS_TZ = ZoneInfo("Asia/Shanghai")

END_OF_DAY = (23, 59)
"""Default clock time for a date-only deadline."""

MAX_FUTURE_DAYS = 400
"""A resolved deadline further out than this is treated as a parse failure. Real
campus deadlines are within a term or two; anything beyond is a mis-parse (a
phone number read as a date, a typo'd year)."""

PAST_TOLERANCE = timedelta(hours=2)
"""How far in the past a deadline may fall before it is rejected. Small window
because a notice is sometimes posted minutes after its own cutoff, but a
deadline days in the past means the phrase was resolved against the wrong week."""

_CN_DIGITS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

_WEEKDAY_CN = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "天": 6,
    "日": 6,
    "1": 0,
    "2": 1,
    "3": 2,
    "4": 3,
    "5": 4,
    "6": 5,
    "7": 6,
}


@dataclass
class ResolvedDeadline:
    """The outcome of resolving one phrase."""

    at: datetime | None
    """Timezone-aware UTC instant, or None when the phrase could not be resolved."""
    is_explicit: bool = True
    """False when the time of day was inferred rather than stated."""
    phrase: str = ""
    basis: str = ""
    """Which rule matched, e.g. "weekday+clock". Shown in the trace panel."""
    note: str | None = None
    """Set when the phrase was understood but rejected, e.g. "in the past"."""


def _cn_number(token: str) -> int | None:
    """Parse an integer written in digits or simple Chinese numerals."""
    token = token.strip()
    if token.isdigit():
        return int(token)
    if not token:
        return None
    # 十, 十二, 二十, 二十三
    if "十" in token:
        head, _, tail = token.partition("十")
        tens = _CN_DIGITS.get(head, 1) if head else 1
        ones = _CN_DIGITS.get(tail, 0) if tail else 0
        return tens * 10 + ones
    total = 0
    for char in token:
        digit = _CN_DIGITS.get(char)
        if digit is None:
            return None
        total = total * 10 + digit
    return total


def _apply_meridiem(hour: int, marker: str, minute: int) -> tuple[int, int]:
    """Map a Chinese day-part word plus an hour onto a 24h clock.

    ``晚上12点`` is the case that matters: see the module docstring. It resolves
    to 23:59 (end of day) rather than 00:00 or 12:00.
    """
    if marker in ("晚上", "晚", "夜里", "夜晚") and hour == 12:
        return END_OF_DAY
    if marker in ("凌晨",):
        return (0 if hour == 12 else hour, minute)
    if marker in ("早上", "上午", "早"):
        return (0 if hour == 12 else hour, minute)
    if marker in ("中午",):
        return (12 if hour == 12 else hour, minute)
    if marker in ("下午", "傍晚", "晚上", "晚", "夜里", "夜晚"):
        return (hour + 12 if hour < 12 else hour, minute)
    return (hour, minute)


_RE_CLOCK = re.compile(
    r"(?P<marker>凌晨|早上|上午|中午|下午|傍晚|晚上|晚|夜里|夜晚)?\s*"
    r"(?P<hour>\d{1,2}|[一二三四五六七八九十两]+)\s*"
    r"(?:[:：]\s*(?P<minute>\d{1,2})"
    r"|[点时]\s*(?P<minute_cn>\d{1,2}|[一二三四五六七八九十两]+)?\s*(?P<half>半)?)"
)

_RE_DATE = re.compile(
    r"(?:(?P<year>20\d{2})\s*[-/年]\s*)?"
    r"(?P<month>\d{1,2}|[一二三四五六七八九十]+)\s*月\s*"
    r"(?P<day>\d{1,2}|[一二三四五六七八九十]+)\s*[日号]?"
    r"|(?P<year2>20\d{2})\s*[-/]\s*(?P<month2>\d{1,2})\s*[-/]\s*(?P<day2>\d{1,2})"
    r"|(?P<month3>\d{1,2})\s*/\s*(?P<day3>\d{1,2})"
)

_RE_WEEKDAY = re.compile(
    r"(?P<offset>这|本|下下|下|上上|上)?\s*(?:周|星期|礼拜)\s*(?P<day>[一二三四五六天日1-7])"
)

_RE_DAYWORD = re.compile(r"今[天日晚早]|明[天日晚早]|后天|大后天|次日|当天")

_RE_RELATIVE = re.compile(
    r"(?P<num>[0-9一二三四五六七八九十两]+)\s*(?P<unit>天|日|周|星期|小时|个?月)\s*(?:内|后|之内|以内)"
)

_RE_SPAN = re.compile(r"(?:本|这)(?:周|星期)内?|(?:本|这)月内?|月底|月末|周末|学期末")

_DAYWORD_OFFSET = {
    "今天": 0,
    "今日": 0,
    "今晚": 0,
    "今早": 0,
    "当天": 0,
    "明天": 1,
    "明日": 1,
    "明晚": 1,
    "明早": 1,
    "次日": 1,
    "后天": 2,
    "大后天": 3,
}


def _clock_from(phrase: str) -> tuple[int, int] | None:
    """Extract an hour and minute from a phrase, if it states one."""
    match = _RE_CLOCK.search(phrase)
    if not match:
        return None
    hour = _cn_number(match.group("hour"))
    if hour is None or hour > 24:
        return None

    minute = 0
    if match.group("minute"):
        minute = int(match.group("minute"))
    elif match.group("minute_cn"):
        minute = _cn_number(match.group("minute_cn")) or 0
    elif match.group("half"):
        minute = 30
    if minute > 59:
        return None

    if hour == 24:
        return END_OF_DAY

    return _apply_meridiem(hour, match.group("marker") or "", minute)


def resolve_deadline(phrase: str, sent_at: datetime) -> ResolvedDeadline:
    """Resolve a Chinese time phrase against the moment the message was sent.

    Args:
        phrase: The verbatim phrase L2 copied out of the message, e.g.
            "周五晚上12点前".
        sent_at: When the message was sent. Must be timezone-aware; it is the
            anchor for every relative expression, which is why the message
            timestamp is stored on the task rather than the extraction time.

    Returns:
        A ResolvedDeadline. ``at`` is None when the phrase could not be resolved
        or when the result failed a sanity check, with ``note`` explaining which.
    """
    if not phrase or not phrase.strip():
        return ResolvedDeadline(None, phrase=phrase or "", basis="empty")
    if sent_at.tzinfo is None:
        raise ValueError("sent_at must be timezone-aware")

    phrase = phrase.strip()
    base = sent_at.astimezone(CAMPUS_TZ)
    clock = _clock_from(phrase)
    explicit = clock is not None
    hour, minute = clock if clock else END_OF_DAY

    target: datetime | None = None
    basis = ""

    # Explicit dates win: they need no anchoring and cannot be off by a week.
    # Three shapes are accepted: "8月10日" / "2026-08-10" / "8/10". A bare
    # "3-5" is a range (exercise numbers, page spans), not March 5th, so the
    # hyphen form is only ever matched with a four-digit year in front.
    if match := _RE_DATE.search(phrase):
        if match.group("month"):
            # "8月10日" / "2026年8月10日" -- the 月 form; year is optional.
            year = int(match.group("year")) if match.group("year") else base.year
            month = _cn_number(match.group("month"))
            day = _cn_number(match.group("day"))
        elif match.group("month2"):
            # "2026-08-10" -- slash/hyphen form with a four-digit year.
            year = int(match.group("year2"))
            month = int(match.group("month2"))
            day = int(match.group("day2"))
        elif match.group("month3"):
            # "8/10" -- bare slash form, no year.
            month = _cn_number(match.group("month3"))
            day = _cn_number(match.group("day3"))
            year = base.year
        else:
            # Matched shape is not one of the three above; nothing usable.
            return ResolvedDeadline(
                None, phrase=phrase, basis="date", note="unrecognized_date_shape"
            )
        if month and day and 1 <= month <= 12 and 1 <= day <= 31:
            try:
                target = base.replace(
                    year=year,
                    month=month,
                    day=day,
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0,
                )
            except ValueError:
                return ResolvedDeadline(
                    None, phrase=phrase, basis="date", note="invalid_calendar_date"
                )
            # A bare "1月5日" sent in December means next January, not a date
            # eleven months past.
            if (
                not match.group("year")
                and not match.group("year2")
                and target < base - timedelta(days=180)
            ):
                target = target.replace(year=year + 1)
            basis = "date+clock" if explicit else "date"

    if target is None and (match := _RE_DAYWORD.search(phrase)):
        word = match.group()
        offset = _DAYWORD_OFFSET.get(word)
        if offset is None:
            offset = _DAYWORD_OFFSET.get(word[0] + "天", 0)
        # 今晚/明晚 imply the evening even with no clock stated.
        if not explicit and word.endswith("晚"):
            hour, minute = END_OF_DAY
        if not explicit and word.endswith("早"):
            hour, minute = 8, 0
        target = (base + timedelta(days=offset)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        basis = "dayword+clock" if explicit else "dayword"

    if target is None and (match := _RE_WEEKDAY.search(phrase)):
        wanted = _WEEKDAY_CN.get(match.group("day"))
        if wanted is not None:
            prefix = (match.group("offset") or "").strip()
            days_ahead = wanted - base.weekday()
            if prefix in ("下", ""):
                # A bare "周五" means the coming Friday. If today *is* Friday,
                # treat it as today -- a teacher saying "周五交" on Friday means
                # today, not a week away.
                if days_ahead < 0:
                    days_ahead += 7
                if prefix == "下":
                    # "下周五" is the Friday of next week, counted from Monday.
                    days_ahead = wanted - base.weekday() + 7
            elif prefix in ("这", "本"):
                if days_ahead < 0:
                    days_ahead += 7
            elif prefix == "下下":
                days_ahead = wanted - base.weekday() + 14
            elif prefix in ("上", "上上"):
                return ResolvedDeadline(
                    None, phrase=phrase, basis="weekday", note="refers_to_past_week"
                )
            target = (base + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            basis = "weekday+clock" if explicit else "weekday"

    if target is None and (match := _RE_RELATIVE.search(phrase)):
        amount = _cn_number(match.group("num"))
        unit = match.group("unit")
        if amount is not None:
            if unit in ("小时",):
                target = base + timedelta(hours=amount)
                basis = "relative_hours"
                explicit = True
            elif unit in ("天", "日"):
                target = (base + timedelta(days=amount)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                basis = "relative_days"
            elif unit in ("周", "星期"):
                target = (base + timedelta(weeks=amount)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                basis = "relative_weeks"
            else:  # 个月 / 月
                target = (base + timedelta(days=30 * amount)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                basis = "relative_months"

    if target is None and (match := _RE_SPAN.search(phrase)):
        span = match.group()
        if span in ("月底", "月末") or span.startswith(("本月", "这月")):
            next_month = base.replace(day=28) + timedelta(days=4)
            last_day = next_month - timedelta(days=next_month.day)
            target = last_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
            basis = "month_end"
        elif span in (
            "本周内",
            "本星期内",
            "这周内",
            "这星期内",
            "本周",
            "本星期",
            "这周",
            "这星期",
            "周末",
        ):
            # "本周内" / "周末" is an interval whose far edge is this week's
            # Sunday -- the last day anything "本周内" could still be due.
            days_ahead = 6 - base.weekday()
            target = (base + timedelta(days=days_ahead)).replace(
                hour=hour, minute=minute, second=0, microsecond=0
            )
            basis = "week_end"
        else:
            # "学期末" / "假期前" have no reliable anchor in code. A confident
            # wrong date is the one failure this resolver exists to avoid, so
            # they resolve to nothing and the pipeline flags the task for
            # confirmation instead of dating it by guesswork.
            return ResolvedDeadline(
                None,
                is_explicit=explicit,
                phrase=phrase,
                basis="span",
                note="ambiguous_span",
            )

    if target is None and clock is not None:
        # A time with no date at all ("12点前交") means today, or tomorrow if
        # that hour has already passed.
        target = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target < base:
            target += timedelta(days=1)
        basis = "clock_only"

    if target is None:
        return ResolvedDeadline(None, phrase=phrase, basis="unmatched")

    # --- sanity checks ----------------------------------------------------
    if target < base - PAST_TOLERANCE:
        return ResolvedDeadline(
            None, is_explicit=explicit, phrase=phrase, basis=basis, note="in_the_past"
        )
    if target > base + timedelta(days=MAX_FUTURE_DAYS):
        return ResolvedDeadline(
            None,
            is_explicit=explicit,
            phrase=phrase,
            basis=basis,
            note="too_far_future",
        )

    return ResolvedDeadline(
        at=target.astimezone(ZoneInfo("UTC")),
        is_explicit=explicit,
        phrase=phrase,
        basis=basis,
    )


__all__ = ["CAMPUS_TZ", "ResolvedDeadline", "resolve_deadline"]
