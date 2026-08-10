"""L4 TimeNormalizer (M2b.1) — port of V1 timeresolve behavior.

Anchors on the SOURCE EVENT timestamp (not LLM/insert/wall time). Uses
zoneinfo for the configured runtime timezone (default Asia/Shanghai), never
fixed +08:00 arithmetic.

V1 conventions preserved:
- 晚上12点 -> 23:59 (end of day)
- 今晚/明晚 (no clock) -> 23:59; 明早 -> 08:00
- bare date -> 23:59 (not explicit)
- past expressions outside tolerance rejected; future > 400 days rejected
- unresolvable phrase -> deadline None (caller forces pending_confirm)
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from campuscue.tasks.models import ResolvedDeadline

MAX_FUTURE_DAYS = 400
PAST_TOLERANCE = timedelta(hours=2)

_MERIDIEM = ("凌晨", "早上", "上午", "中午", "下午", "傍晚", "晚上", "晚", "夜里", "夜晚")

_WEEKDAY_MAP = {
    "周一": 0, "星期二": 1, "礼拜三": 2, "周四": 3, "周五": 4, "星期六": 5, "周日": 6, "周天": 6,
}
_WEEKDAY_ALIAS = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
}

# weekday + optional clock: "周五晚上12点" / "这周五" / "下周三"
_WEEKDAY_RE = re.compile(
    r"(?P<week>(?:下下|下|这|本)?)\s*"
    r"(?:周|星期|礼拜)\s*(?P<day>[一二三四五六日天])"
    r"(?P<rest>.*)$"
)
# clock: "晚上12点" "12:30" "9点"
_CLOCK_RE = re.compile(
    r"(?P<marker>凌晨|早上|上午|中午|下午|傍晚|晚上|晚|夜里|夜晚)?\s*"
    r"(?P<hour>\d{1,2})\s*[:：点]\s*(?P<minute>\d{1,2})?\s*分?"
)
# relative day words
_RELATIVE_DAY = {
    "今天": 0, "今晚": 0, "今夜": 0, "昨天": -1, "前天": -2, "明天": 1, "明晚": 1, "明早": 1, "后天": 2, "大后天": 3,
}
# bare date: "8月10日" / "2026年8月10日" / "2026-08-10" / "8/10"
_DATE_RE = re.compile(
    r"(?:(?P<year>20\d{2})\s*[-/年]\s*)?"
    r"(?P<month>\d{1,2})\s*月\s*(?P<day>\d{1,2})\s*日?"
    r"|(?P<y2>20\d{2})\s*[-/]\s*(?P<m2>\d{1,2})\s*[-/]\s*(?P<d2>\d{1,2})"
    r"|(?P<m3>\d{1,2})\s*/\s*(?P<d3>\d{1,2})"
)
_MONTH_END_RE = re.compile(r"月底|月末")


def resolve_deadline(phrase: str, current_time: datetime, tz: ZoneInfo) -> ResolvedDeadline:
    """Resolve a Chinese deadline phrase anchored at current_time (aware, any tz)."""
    if not phrase or not phrase.strip():
        return ResolvedDeadline(deadline=None, is_explicit=False, reason="no_phrase")
    local_now = current_time.astimezone(tz)
    stripped = phrase.strip().rstrip("前").strip()

    # explicit date first (cannot be off by a week)
    if m := _DATE_RE.search(stripped):
        has_explicit_year = bool(m.group("year") or m.group("y2"))
        year = int(m.group("year")) if m.group("year") else int(m.group("y2")) if m.group("y2") else local_now.year
        if m.group("month"):
            month, day = int(m.group("month")), int(m.group("day"))
        elif m.group("m2"):
            month, day = int(m.group("m2")), int(m.group("d2"))
        else:
            month, day = int(m.group("m3")), int(m.group("d3"))
        try:
            dt = local_now.replace(year=year, month=month, day=day, hour=23, minute=59, second=0, microsecond=0)
        except ValueError:
            return ResolvedDeadline(deadline=None, is_explicit=False, reason="invalid_date")
        if dt < local_now - PAST_TOLERANCE:
            # M2b.1.1 (Finding F): ONLY yearless dates may use cross-year
            # inference ("8月10日" after Aug 10 -> next year). An EXPLICITLY
            # supplied past year/date (e.g. "2026年8月9日" on 2026-08-10) must
            # be rejected as past — never silently rewritten to next year.
            if has_explicit_year:
                return ResolvedDeadline(deadline=None, is_explicit=False, reason="past_rejected:explicit_date")
            dt = dt.replace(year=year + 1)  # cross-year: "8月10日" after Aug 10 -> next year
        return _check_future(dt, local_now, is_explicit=True, reason="explicit_date")

    if _MONTH_END_RE.search(stripped):
        next_month_first = (local_now.replace(day=28) + timedelta(days=4)).replace(day=1)
        dt = next_month_first - timedelta(days=1)
        dt = dt.replace(hour=23, minute=59)
        return _check_future(dt, local_now, is_explicit=False, reason="month_end")

    if m := _WEEKDAY_RE.match(stripped):
        day_idx = _WEEKDAY_ALIAS[m.group("day")]
        week_shift = {"下下": 14, "下": 7, "这": 0, "本": 0, "": 0}.get(m.group("week"), 0)
        days_ahead = (day_idx - local_now.weekday()) % 7
        if week_shift == 0 and days_ahead == 0:
            days_ahead = 7  # "周五" said on Friday means next Friday
        dt = (local_now + timedelta(days=days_ahead + week_shift)).replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        is_explicit = False
        reason = f"weekday:{m.group('day')}"
        if m.group("rest"):
            if cm := _CLOCK_RE.search(m.group("rest")):
                hour = int(cm.group("hour"))
                minute = int(cm.group("minute") or 0)
                marker = cm.group("marker")
                if marker in ("晚上", "晚", "夜里", "夜晚") and hour == 12:
                    hour, minute = 23, 59  # 晚上12点 -> 23:59
                elif marker in ("下午", "傍晚", "晚上", "晚", "夜里", "夜晚") and hour < 12:
                    hour += 12
                elif marker in ("凌晨", "早上", "上午") and hour == 12:
                    hour = 0
                dt = dt.replace(hour=hour, minute=minute)
                is_explicit = True
                reason = "weekday+clock"
        return _check_future(dt, local_now, is_explicit=is_explicit, reason=reason)

    # relative day words
    for word, offset in _RELATIVE_DAY.items():
        if word in stripped:
            dt = (local_now + timedelta(days=offset)).replace(hour=23, minute=59, second=0, microsecond=0)
            is_explicit = False
            reason = f"relative:{word}"
            if cm := _CLOCK_RE.search(stripped):
                hour = int(cm.group("hour"))
                minute = int(cm.group("minute") or 0)
                marker = cm.group("marker")
                if marker in ("晚上", "晚", "夜里", "夜晚") and hour == 12:
                    hour, minute = 23, 59
                elif marker in ("下午", "傍晚", "晚上", "晚", "夜里", "夜晚") and hour < 12:
                    hour += 12
                elif marker in ("凌晨", "早上", "上午") and hour == 12:
                    hour = 0
                dt = dt.replace(hour=hour, minute=minute)
                is_explicit = True
                reason = f"relative+clock:{word}"
            if word == "明早" and not cm:
                dt = dt.replace(hour=8, minute=0)
                is_explicit = True
                reason = "relative:明早"
            return _check_future(dt, local_now, is_explicit=is_explicit, reason=reason)

    # bare clock only: "晚上12点前" -> today
    if cm := _CLOCK_RE.search(stripped):
        hour = int(cm.group("hour"))
        minute = int(cm.group("minute") or 0)
        marker = cm.group("marker")
        if marker in ("晚上", "晚", "夜里", "夜晚") and hour == 12:
            hour, minute = 23, 59
        elif marker in ("下午", "傍晚", "晚上", "晚", "夜里", "夜晚") and hour < 12:
            hour += 12
        dt = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return _check_future(dt, local_now, is_explicit=True, reason="clock")

    return ResolvedDeadline(deadline=None, is_explicit=False, reason="unresolved")


def _check_future(dt: datetime, local_now: datetime, *, is_explicit: bool, reason: str) -> ResolvedDeadline:
    if dt < local_now - PAST_TOLERANCE:
        return ResolvedDeadline(deadline=None, is_explicit=False, reason=f"past_rejected:{reason}")
    if dt > local_now + timedelta(days=MAX_FUTURE_DAYS):
        return ResolvedDeadline(deadline=None, is_explicit=False, reason=f"future_rejected:{reason}")
    return ResolvedDeadline(deadline=dt.astimezone(timezone.utc), is_explicit=is_explicit, reason=reason)
