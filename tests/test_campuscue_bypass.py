"""The bypass contract: CampusCue must see non-woken group messages, and the
bot must stay silent about them.

CampusCue's whole premise is reading messages nobody addressed to the bot. That
works because ``WakingCheckStage`` sets ``is_wake = True`` when a plugin filter
passes but leaves ``is_at_or_wake_command`` alone, while ``ProcessStage`` gates
the default LLM reply on ``is_at_or_wake_command``. Those are two separate flags
in upstream code that a refactor could easily collapse into one -- and if that
happened the bot would start replying to every message in every watched group.

These tests pin the distinction down so the failure shows up here instead of in
front of a room of judges.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.filter.event_message_type import (
    EventMessageType,
    EventMessageTypeFilter,
)


def make_group_event(
    text: str = "实验三报告周五晚上12点前提交",
    sender_id: str = "10001",
    self_id: str = "99999",
) -> AstrMessageEvent:
    """A plain group message that does not mention the bot."""
    msg = AstrBotMessage()
    msg.type = MessageType.GROUP_MESSAGE
    msg.self_id = self_id
    msg.session_id = "group-7788"
    msg.group_id = "7788"
    msg.message_id = "m-1"
    msg.sender = MessageMember(user_id=sender_id, nickname="张老师")
    msg.message = [Plain(text)]
    msg.message_str = text
    msg.raw_message = text
    msg.timestamp = 1785000000

    return AstrMessageEvent(
        message_str=text,
        message_obj=msg,
        platform_meta=PlatformMetadata(
            name="aiocqhttp", description="test", id="aiocqhttp"
        ),
        session_id=msg.session_id,
    )


def test_group_filter_matches_plain_group_message():
    """The filter CampusCue registers with must accept an un-@ed group message.

    If this fails the observer never runs and the product has no input.
    """
    event = make_group_event()
    group_filter = EventMessageTypeFilter(EventMessageType.GROUP_MESSAGE)

    assert group_filter.filter(event, SimpleNamespace()) is True


def test_plain_group_message_is_not_marked_as_addressing_the_bot():
    """A fresh group event must not look like a wake command.

    ``ProcessStage`` only falls through to the default LLM reply when
    ``is_at_or_wake_command`` is true. Upstream documents the split in
    astr_message_event.py: "插件注册的事件监听器会让 is_wake 设为 True, 但是不会
    让这个属性置为 True". This asserts the two flags stay independent, which is
    what keeps the bot quiet in watched groups.
    """
    event = make_group_event()

    assert event.is_at_or_wake_command is False
    assert event.is_wake is False

    # Simulate what WakingCheckStage does when a plugin filter passes.
    event.is_wake = True

    assert event.is_at_or_wake_command is False, (
        "activating a plugin handler must not make the event look like the user "
        "addressed the bot, or CampusCue would trigger a reply to every message"
    )


def test_default_llm_reply_condition_stays_false_for_observed_message():
    """Reproduce ProcessStage's gate verbatim and assert it does not open.

    ProcessStage.process:
        if not event._has_send_oper and event.is_at_or_wake_command
           and not event.call_llm:
    """
    event = make_group_event()
    event.is_wake = True  # what the bypass handler causes

    would_reply = (
        not event._has_send_oper and event.is_at_or_wake_command and not event.call_llm
    )

    assert would_reply is False


@pytest.fixture
def no_pipeline(monkeypatch):
    """Cut the extraction pipeline off from the background task.

    Without this the handoff assertion below awaits ``_extract`` for real, and
    ``_extract`` imports ``process_message``, which writes to whatever database
    ``campuscue.store`` is pointed at -- with no db fixture in this file, that is
    the live ``data/data_v4.db``. The suite left a fake source and a fake task in
    the running app's board, and called the real LLM to do it.

    What this file is about is the handoff itself: that the handler returns
    nothing and hands work off instead of awaiting it inline. What the pipeline
    then does with the message belongs to the extractor tests.
    """
    from campuscue.extractor import pipeline

    seen: list[str] = []

    async def fake_process(ctx, client=None):
        seen.append(ctx.text)

    monkeypatch.setattr(pipeline, "process_message", fake_process)
    return seen


@pytest.mark.asyncio
async def test_observer_yields_nothing_and_schedules_background_work(no_pipeline):
    """The handler must produce no result and must not block the pipeline."""
    from astrbot.builtin_stars.campuscue.main import CampusCue

    star = CampusCue(context=SimpleNamespace())
    event = make_group_event()

    result = await star.observe_group_message(event)

    # A returned/yielded value would become a message sent to the group.
    assert result is None
    assert event.get_result() is None
    assert event._has_send_oper is False
    assert event.is_stopped() is False, (
        "stopping the event would also cancel legitimate @-mention conversations"
    )

    assert star._observed == 1
    assert len(star._pending) == 1  # work was handed off, not awaited inline

    await asyncio.gather(*star._pending, return_exceptions=True)

    # The message reached the pipeline, and reached it through the stub -- if the
    # import in _extract ever stops resolving through the module attribute this
    # goes empty, which is the signal that the stub is no longer taking effect.
    assert no_pipeline == ["实验三报告周五晚上12点前提交"]


@pytest.mark.asyncio
async def test_observer_ignores_the_bots_own_messages():
    """A reminder the bot pushed must not be re-extracted into a new task."""
    from astrbot.builtin_stars.campuscue.main import CampusCue

    star = CampusCue(context=SimpleNamespace())
    event = make_group_event(sender_id="99999", self_id="99999")

    await star.observe_group_message(event)

    assert star._observed == 0
    assert not star._pending


@pytest.mark.asyncio
async def test_observer_ignores_empty_messages():
    """Stickers and images arrive with an empty message_str; skip them for now."""
    from astrbot.builtin_stars.campuscue.main import CampusCue

    star = CampusCue(context=SimpleNamespace())
    event = make_group_event(text="   ")

    await star.observe_group_message(event)

    assert star._observed == 0
    assert not star._pending


@pytest.mark.asyncio
async def test_observer_logs_metadata_without_message_or_sender(
    no_pipeline, monkeypatch
):
    """Debug logging must not create a second plaintext group-message store."""
    from astrbot.builtin_stars.campuscue import main as plugin

    records: list[tuple[object, ...]] = []
    fake_logger = SimpleNamespace(
        debug=lambda *args, **kwargs: records.append(args),
        exception=lambda *args, **kwargs: records.append(args),
    )
    monkeypatch.setattr(plugin, "logger", fake_logger)

    secret = "仅供本群：奖学金材料和身份证号明天交"
    star = plugin.CampusCue(context=SimpleNamespace())
    event = make_group_event(text=secret)

    await star.observe_group_message(event)
    await asyncio.gather(*star._pending, return_exceptions=True)

    rendered = repr(records)
    assert secret not in rendered
    assert event.get_sender_name() not in rendered
    assert event.get_sender_id() not in rendered
    assert event.unified_msg_origin not in rendered
    assert str(len(secret)) in rendered
