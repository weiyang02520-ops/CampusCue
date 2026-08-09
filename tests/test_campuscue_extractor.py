"""L1 prefilter and L3 time resolution.

The time resolver is the part of CampusCue most likely to be quietly wrong: a
deadline resolved one week late still looks plausible on a task card, and the
student only finds out by missing the deadline. So the weekday cases are pinned
down against a known anchor date rather than checked by eye.

Anchor for every case below: 2026-07-27 14:23 Asia/Shanghai, a Monday. Chosen to
match the probe run, and because Monday makes "本周五" and "下周五" resolve to
visibly different weeks.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from campuscue.extractor.prefilter import prefilter
from campuscue.extractor.timeresolve import CAMPUS_TZ, resolve_deadline

MONDAY = datetime(2026, 7, 27, 14, 23, tzinfo=CAMPUS_TZ)


def local(resolved) -> datetime:
    """Resolved deadlines are UTC; compare them in campus wall-clock time."""
    assert resolved.at is not None, f"failed to resolve: {resolved}"
    return resolved.at.astimezone(CAMPUS_TZ)


def test_malformed_model_output_is_kept_for_trace_but_not_exception_text():
    from campuscue.extractor.llm import ExtractionError, _parse_content

    private_output = "学生姓名和手机号，仅供本群处理"

    with pytest.raises(ExtractionError) as caught:
        _parse_content(private_output)

    assert caught.value.code == "invalid_model_output"
    assert caught.value.raw_response == private_output
    assert private_output not in str(caught.value)


@pytest.mark.asyncio
async def test_pipeline_crash_log_does_not_contain_message_text(monkeypatch):
    """An unexpected crash is diagnosable without copying private chat to logs."""
    from campuscue.extractor import pipeline

    records: list[tuple[object, ...]] = []

    async def crash(ctx, *, client):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(pipeline, "_process", crash)
    monkeypatch.setattr(
        pipeline,
        "logger",
        type("Logger", (), {"exception": lambda self, *args: records.append(args)})(),
    )
    secret = "仅供本群：家庭住址和手机号不要外传"
    ctx = pipeline.MessageContext(
        umo="qq:GroupMessage:private",
        text=secret,
        sent_at=MONDAY,
        message_id="message-42",
        sender_name="真实姓名",
    )

    result = await pipeline.process_message(ctx, client=None)

    assert result.outcome == "pipeline_error"
    rendered = repr(records)
    assert secret not in rendered
    assert ctx.sender_name not in rendered
    assert ctx.umo not in rendered
    assert ctx.message_id in rendered
    assert str(len(secret)) in rendered


# =========================================================================
# L3 -- the three demo scenarios
# =========================================================================


def test_homework_friday_midnight_means_end_of_friday():
    """ "周五晚上12点前" -- the single most common phrasing, and the one where
    getting the convention wrong shifts the deadline a whole day."""
    got = local(resolve_deadline("周五晚上12点前", MONDAY))

    assert (got.month, got.day) == (7, 31), "Friday of the same week"
    assert (got.hour, got.minute) == (23, 59), (
        "晚上12点 must mean the end of Friday, not Friday 00:00 -- resolving it "
        "to midnight would fire the reminder a day before the work is due"
    )


def test_exam_next_tuesday_with_clock():
    """ "下周二8:30" from a Monday -- next week's Tuesday, not tomorrow."""
    got = local(resolve_deadline("下周二8:30", MONDAY))

    assert (got.month, got.day) == (8, 4)
    assert (got.hour, got.minute) == (8, 30)


def test_competition_explicit_date_defaults_to_end_of_day():
    """ "8月10日" states no time, so it becomes 23:59 and is flagged inferred."""
    resolved = resolve_deadline("8月10日", MONDAY)
    got = local(resolved)

    assert (got.month, got.day) == (8, 10)
    assert (got.hour, got.minute) == (23, 59)
    assert resolved.is_explicit is False, (
        "the time of day was guessed, and the UI needs to say so"
    )


# =========================================================================
# L3 -- weekday arithmetic, where an off-by-one-week bug would hide
# =========================================================================


@pytest.mark.parametrize(
    ("phrase", "expected_day"),
    [
        ("周五", 31),  # bare -> this coming Friday
        ("本周五", 31),
        ("这周五", 31),
        ("下周五", 8 - 1),  # Aug 7 -> handled below
    ],
)
def test_weekday_variants(phrase: str, expected_day: int):
    got = local(resolve_deadline(phrase, MONDAY))
    if phrase == "下周五":
        assert (got.month, got.day) == (8, 7)
    else:
        assert (got.month, got.day) == (7, expected_day)


def test_bare_weekday_matching_today_means_today():
    """A teacher saying "周五交" on a Friday means today, not next week."""
    friday = datetime(2026, 7, 31, 9, 0, tzinfo=CAMPUS_TZ)
    got = local(resolve_deadline("周五", friday))

    assert (got.month, got.day) == (7, 31)


def test_next_week_monday_from_monday_is_seven_days_later():
    got = local(resolve_deadline("下周一", MONDAY))

    assert (got.month, got.day) == (8, 3)


def test_week_after_next():
    got = local(resolve_deadline("下下周三", MONDAY))

    assert (got.month, got.day) == (8, 12)


def test_last_week_is_rejected_not_guessed():
    resolved = resolve_deadline("上周五", MONDAY)

    assert resolved.at is None
    assert resolved.note == "refers_to_past_week"


# =========================================================================
# L3 -- day words, clocks, relative spans
# =========================================================================


@pytest.mark.parametrize(
    ("phrase", "day", "hour"),
    [
        ("今晚", 27, 23),
        ("明天", 28, 23),
        ("明晚12点", 28, 23),
        ("后天", 29, 23),
        ("大后天", 30, 23),
    ],
)
def test_day_words(phrase: str, day: int, hour: int):
    got = local(resolve_deadline(phrase, MONDAY))

    assert got.day == day
    assert got.hour == hour


@pytest.mark.parametrize(
    ("phrase", "hour", "minute"),
    [
        ("下午3点", 15, 0),
        ("上午9点", 9, 0),
        ("中午12点半", 12, 30),
        ("晚上8点", 20, 0),
        ("23:59", 23, 59),
        ("八点", 8, 0),
        ("十点半", 10, 30),
    ],
)
def test_clock_forms(phrase: str, hour: int, minute: int):
    got = local(resolve_deadline(phrase, MONDAY))

    assert (got.hour, got.minute) == (hour, minute)


def test_clock_only_already_passed_today_rolls_to_tomorrow():
    """Anchor is 14:23, so "9点" cannot mean today."""
    got = local(resolve_deadline("9点", MONDAY))

    assert got.day == 28
    assert got.hour == 9


def test_relative_hours_and_days():
    assert local(resolve_deadline("24小时内", MONDAY)).day == 28
    assert local(resolve_deadline("三天内", MONDAY)).day == 30
    assert local(resolve_deadline("两周后", MONDAY)).day == 10


def test_month_end():
    got = local(resolve_deadline("月底", MONDAY))

    assert (got.month, got.day) == (7, 31)


def test_this_week_span_resolves_to_sunday():
    got = local(resolve_deadline("本周内", MONDAY))

    assert (got.month, got.day) == (8, 2)


# =========================================================================
# L3 -- rejection paths. Silence is better than a wrong date.
# =========================================================================


def test_bare_date_in_the_past_rolls_to_next_year():
    """ "1月5日" sent in December means the coming January."""
    december = datetime(2026, 12, 20, 10, 0, tzinfo=CAMPUS_TZ)
    got = local(resolve_deadline("1月5日", december))

    assert (got.year, got.month, got.day) == (2027, 1, 5)


def test_recent_past_deadline_is_rejected():
    resolved = resolve_deadline("今天上午9点", MONDAY)

    assert resolved.at is None
    assert resolved.note == "in_the_past"


def test_invalid_calendar_date_is_rejected():
    resolved = resolve_deadline("2月30日", MONDAY)

    assert resolved.at is None
    assert resolved.note == "invalid_calendar_date"


def test_unparseable_phrase_returns_none_rather_than_a_guess():
    resolved = resolve_deadline("过段时间", MONDAY)

    assert resolved.at is None
    assert resolved.basis == "unmatched"


def test_empty_phrase():
    assert resolve_deadline("", MONDAY).at is None


def test_naive_timestamp_is_a_programming_error():
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_deadline("周五", datetime(2026, 7, 27, 14, 23))


def test_resolved_deadline_is_utc():
    """Storage is UTC everywhere, matching astrbot's own convention."""
    resolved = resolve_deadline("周五晚上12点前", MONDAY)

    assert resolved.at is not None
    assert resolved.at.tzinfo is not None
    assert resolved.at.utcoffset().total_seconds() == 0
    # 2026-07-31 23:59 +08:00 == 2026-07-31 15:59 UTC
    assert (resolved.at.hour, resolved.at.minute) == (15, 59)


# =========================================================================
# L1 -- the asymmetry: a missed deadline is unrecoverable, a wasted call is free
# =========================================================================


@pytest.mark.parametrize(
    "text",
    [
        "实验三报告周五晚上12点前提交，交到学习通",
        "通知：高数考试，下周二8:30，3教405，带身份证和校园卡",
        "第八届大学生创新创业大赛开始报名了，截止8月10日",
        "报告周五交",  # no deadline keyword at all, but real homework
        "@全体成员 明天下午的讲座记得参加",
        "作业截止时间延长到下周一",
        # Terse homework: no 作业, no time, no deadline word. Real teachers do
        # this constantly and L1 used to drop all of it.
        "完成第35页到第40页",
        "把课本第35页到第40页的题做完",
        "习题3-5、3-7做一下",
        "第三章课后题写完",
        "背诵第5课",
        "预习第三章",
    ],
)
def test_prefilter_passes_real_affairs(text: str):
    result = prefilter(text)

    assert result.passed, f"L1 would have silently dropped a real task: {text!r}"


@pytest.mark.parametrize(
    "text",
    [
        "哈哈哈哈",
        "谢谢老师",
        "收到",
        "好的",
        "666",
        "在吗",
        "晚安",
        "这次作业好难啊",  # affair word alone is not an affair
        # A page reference on its own is a coursework hint, not an assignment.
        "答案在第35页",
        "我第35页不会做",
    ],
)
def test_prefilter_rejects_chatter(text: str):
    result = prefilter(text)

    assert not result.passed, f"L1 would waste a call on chatter: {text!r}"


def test_lunch_invitation_with_weekday_still_passes_and_that_is_accepted():
    """ "周五一起去吃火锅吗" carries a real time expression, so L1 lets it through
    and L2 correctly answers is_task=false (verified in the probe run).

    Documented as intended behaviour rather than papered over: L1 cannot tell
    intent from a weekday alone, and paying ~430 tokens beats teaching it a rule
    that would also drop "周五交作业".
    """
    assert prefilter("周五一起去吃火锅吗").passed


def test_authority_sender_lowers_the_bar():
    """A teacher saying something vaguely affair-like deserves a look."""
    text = "这次的材料记得准备一下"

    assert prefilter(text, is_authority_sender=True).passed
    assert (
        prefilter(text, is_authority_sender=False).score
        < prefilter(text, is_authority_sender=True).score
    )


def test_prefilter_records_why_it_passed():
    """The hits dict is the first panel of the trace shown to the student."""
    result = prefilter("实验三报告周五晚上12点前提交", is_authority_sender=True)
    hits = result.as_hits_json()

    assert "提交" in hits["action_words"]
    assert any("weekday" in t for t in hits["time_expressions"])
    assert any("clock" in t for t in hits["time_expressions"])
    assert hits["authority_sender"] is True
    assert hits["score"] > 0


def test_too_short_and_too_long_are_skipped():
    assert prefilter("好").reject_reason == "too_short"
    assert prefilter("交" * 3000).reject_reason == "too_long"
