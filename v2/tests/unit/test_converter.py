"""Unit tests: OneBot payload -> CampusEvent conversion (pure function)."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from campuscue.adapters.onebot.converter import (
    ConversionResult,
    ValidationError,
    convert_message,
)
from campuscue.core.events import ConversationType, EventType, SegmentType

ADAPTER_ID = "onebot:test"


def _payload(**overrides):
    base = {
        "post_type": "message",
        "self_id": 10001,
        "message_id": 10086,
        "message_type": "group",
        "group_id": 123456,
        "sender": {"user_id": 555, "card": "同学A", "nickname": "同学A"},
        "time": 1723200000,
        "message": [{"type": "text", "data": {"text": "hello"}}],
    }
    base.update(overrides)
    return base


def _fixed_id():
    return "fixed-id"


def _fixed_clock():
    return datetime(2026, 8, 9, 12, 0, 0, tzinfo=timezone.utc)


class TestGroupText:
    def test_group_text_hello(self):
        ev = convert_message(_payload(), adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.platform == "onebot"
        assert ev.adapter_id == ADAPTER_ID
        assert ev.event_type == EventType.GROUP_MESSAGE
        assert ev.conversation_type == ConversationType.GROUP
        assert ev.conversation_id == "123456"
        assert ev.group_id == "123456"
        assert ev.self_id == "10001"
        assert ev.message_id == "10086"
        assert ev.sender_id == "555"
        assert ev.sender_name == "同学A"
        assert ev.text == "hello"
        assert ev.timestamp.tzinfo is not None
        assert ev.timestamp.utcoffset().total_seconds() == 0  # UTC aware

    def test_ids_are_strings(self):
        ev = convert_message(_payload(), adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert isinstance(ev.self_id, str)
        assert isinstance(ev.message_id, str)
        assert isinstance(ev.conversation_id, str)
        assert isinstance(ev.sender_id, str)
        assert isinstance(ev.group_id, str)

    def test_timestamp_timezone_aware_utc(self):
        ev = convert_message(_payload(), adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.timestamp == datetime.fromtimestamp(1723200000, tz=timezone.utc)

    def test_injectable_clock_on_missing_time(self):
        payload = _payload()
        del payload["time"]
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.timestamp == _fixed_clock()

    def test_injectable_id_factory(self):
        ev = convert_message(_payload(), adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.event_id == "fixed-id"
        assert ev.trace_id == "fixed-id"

    def test_group_id_none_for_private(self):
        ev = convert_message(_payload(message_type="private", user_id=777, group_id=None),
                             adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.conversation_type == ConversationType.PRIVATE
        assert ev.conversation_id == "777"
        assert ev.group_id is None


class TestPrivateText:
    def test_private_text(self):
        ev = convert_message(
            _payload(message_type="private", user_id=777, group_id=None, sender={"user_id": 777, "nickname": "我"}),
            adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock,
        )
        assert ev.event_type == EventType.PRIVATE_MESSAGE
        assert ev.conversation_id == "777"
        assert ev.text == "hello"


class TestSegments:
    def test_multiple_text_segments_order_preserved(self):
        payload = _payload(message=[
            {"type": "text", "data": {"text": "高数"}},
            {"type": "text", "data": {"text": "作业"}},
        ])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.text == "高数作业"
        assert [s.type for s in ev.segments] == [SegmentType.TEXT, SegmentType.TEXT]

    def test_text_at_text_order_preserved(self):
        payload = _payload(message=[
            {"type": "text", "data": {"text": "你好"}},
            {"type": "at", "data": {"qq": "555"}},
            {"type": "text", "data": {"text": "请交作业"}},
        ])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.text == "你好请交作业"
        assert [s.type for s in ev.segments] == [SegmentType.TEXT, SegmentType.AT, SegmentType.TEXT]
        assert ev.segments[1].data == {"qq": "555"}

    def test_reply_segment(self):
        payload = _payload(message=[
            {"type": "reply", "data": {"id": "10000"}},
            {"type": "text", "data": {"text": "收到"}},
        ])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.segments[0].type == SegmentType.REPLY
        assert ev.segments[0].data == {"id": "10000"}
        assert ev.text == "收到"

    def test_image_segment(self):
        payload = _payload(message=[
            {"type": "image", "data": {"url": "http://x", "file": "abc.png"}},
            {"type": "text", "data": {"text": "图"}},
        ])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.segments[0].type == SegmentType.IMAGE
        assert ev.segments[0].data["file"] == "abc.png"
        assert ev.text == "图"

    def test_unsupported_segment_mapped_unknown(self):
        payload = _payload(message=[
            {"type": "face", "data": {"id": "1"}},
            {"type": "text", "data": {"text": "hi"}},
        ])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.segments[0].type == SegmentType.UNKNOWN
        assert ev.segments[0].data["raw_type"] == "face"
        assert ev.text == "hi"

    def test_malformed_segment_skipped_not_crash(self):
        payload = _payload(message=[{"type": "text"}, "not-a-dict", {"type": "text", "data": {"text": "ok"}}])
        ev = convert_message(payload, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)
        assert ev.text == "ok"


class TestValidation:
    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            convert_message({"self_id": 1}, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)

    def test_missing_sender(self):
        p = _payload()
        del p["sender"]
        with pytest.raises(ValidationError):
            convert_message(p, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)

    def test_non_array_message_rejected(self):
        p = _payload(message="hello in string form")
        with pytest.raises(ValidationError, match="array"):
            convert_message(p, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)

    def test_unsupported_message_type(self):
        p = _payload(message_type="channel")
        with pytest.raises(ValidationError, match="message_type"):
            convert_message(p, adapter_id=ADAPTER_ID, id_factory=_fixed_id, clock=_fixed_clock)


class TestFrameClassification:
    from campuscue.adapters.onebot.converter import (
        ACTION_RESPONSE,
        EVENT,
        IGNORED_META,
        UNKNOWN,
        classify_frame,
    )

    def test_message_event_is_event(self):
        assert TestFrameClassification.classify_frame(_payload()) == self.EVENT

    def test_message_sent_is_event(self):
        assert TestFrameClassification.classify_frame({"post_type": "message_sent", "message_type": "group"}) == self.EVENT

    def test_meta_event_is_ignored(self):
        assert TestFrameClassification.classify_frame({"post_type": "meta_event", "meta_event_type": "lifecycle"}) == self.IGNORED_META
        assert TestFrameClassification.classify_frame({"post_type": "meta_event", "meta_event_type": "heartbeat"}) == self.IGNORED_META

    def test_notice_and_request_ignored(self):
        assert TestFrameClassification.classify_frame({"post_type": "notice", "notice_type": "group_increase"}) == self.IGNORED_META
        assert TestFrameClassification.classify_frame({"post_type": "request", "request_type": "friend"}) == self.IGNORED_META

    def test_action_response_classified(self):
        assert TestFrameClassification.classify_frame({"status": "ok", "retcode": 0, "echo": "abc"}) == self.ACTION_RESPONSE

    def test_unknown_json(self):
        assert TestFrameClassification.classify_frame({"foo": "bar"}) == self.UNKNOWN
        assert TestFrameClassification.classify_frame([1, 2, 3]) == self.UNKNOWN
        assert TestFrameClassification.classify_frame("nope") == self.UNKNOWN
        assert TestFrameClassification.classify_frame(None) == self.UNKNOWN

    def test_action_response_never_becomes_event(self):
        # an action response must not pass the message converter path
        p = {"status": "ok", "retcode": 0, "echo": "abc", "data": {"message_id": 9}}
        assert TestFrameClassification.classify_frame(p) == self.ACTION_RESPONSE
