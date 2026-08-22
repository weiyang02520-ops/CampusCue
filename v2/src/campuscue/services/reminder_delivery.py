"""Platform delivery boundary for M7.2 reminders.

This module resolves a reminder's canonical source and formats a deterministic
privacy-safe message. It deliberately does not construct OneBot protocol
payloads; the existing adapter owns that boundary.
"""

from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

from campuscue.adapters.onebot.adapter import ActionFailure
from campuscue.core.events import ConversationType
from campuscue.core.outbound import OutgoingMessage
from campuscue.repositories.repositories import NotFoundError, SourceRepository
from campuscue.storage.models import Reminder, Task


class ReminderDeliveryError(Exception):
    """Safe, classified delivery failure suitable for Reminder.error."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class OneBotReminderDelivery:
    """Source-scoped OneBot GROUP reminder delivery."""

    def __init__(self, adapter, sources: SourceRepository, *, timezone: ZoneInfo) -> None:
        self._adapter = adapter
        self._sources = sources
        self._tz = timezone

    async def deliver(self, *, reminder: Reminder, task: Task) -> None:
        if task.source_id is None:
            raise ReminderDeliveryError("delivery:invalid_target")
        try:
            source = await self._sources.get(task.source_id)
        except NotFoundError:
            raise ReminderDeliveryError("delivery:source_missing") from None
        if source.deleted_at is not None:
            raise ReminderDeliveryError("delivery:source_deleted")
        if not source.enabled:
            raise ReminderDeliveryError("delivery:source_disabled")
        if source.platform != "onebot":
            raise ReminderDeliveryError("delivery:unsupported_platform")
        if not source.conversation_id.isdigit() or int(source.conversation_id) <= 0:
            raise ReminderDeliveryError("delivery:invalid_target")
        status = self._adapter.status()
        if not status.get("connected"):
            raise ReminderDeliveryError("delivery:adapter_disconnected")

        try:
            await self._adapter.send(
                OutgoingMessage(
                    conversation_id=source.conversation_id,
                    conversation_type=ConversationType.GROUP,
                    text=self._format(task),
                )
            )
        except ActionFailure as exc:
            reason = str(exc).lower()
            if "timed out" in reason or "timeout" in reason:
                code = "delivery:action_timeout"
            elif "connection" in reason or "closed" in reason:
                code = "delivery:adapter_disconnected"
            else:
                code = "delivery:action_failed"
            raise ReminderDeliveryError(code) from None
        except Exception:
            raise ReminderDeliveryError("delivery:action_failed") from None

    def _format(self, task: Task) -> str:
        lines = ["CampusCue 提醒", task.title]
        if task.course:
            lines.append(f"课程：{task.course}")
        if task.deadline is not None:
            local = task.deadline.astimezone(timezone.utc).astimezone(self._tz)
            lines.append(f"截止时间：{local:%Y-%m-%d %H:%M}")
        return "\n".join(lines)
