"""Delivery: where a detection goes the moment it is found.

Two things live here, because they answer the same question -- "the pipeline just
found something useful, who hears about it?"

1. One designated session, not the source group
-----------------------------------------------
The obvious delivery address is the group the message came from, and it is the
wrong one. Pushing "检测到作业" back into 软件工程课程群 tells thirty classmates
what the student's own assistant noticed, and in a real course group a bot that
talks is a bot that gets kicked. So every push goes to one designated umo -- the
student's own chat with the bot -- and the source group is only ever read.

The target is a single global value rather than a per-group preference: there is
one student behind this process, and letting twelve groups each name a different
destination just means twelve ways to send the notice somewhere nobody reads.

2. Announce at detection, not only before the deadline
------------------------------------------------------
The deadline lead ("提前一天") is still there, but it is no longer the only
channel and no longer the primary one. A lead-time-only design means the student
learns about a Friday deadline on Thursday even though the pipeline knew on
Monday, and worse, it has nothing to say at all about a notice with no resolvable
date. Announcing at detection makes the product's actual claim -- "I read the
group so you do not have to" -- observable within seconds of the teacher typing.

Nothing in this module raises, and nothing in it blocks for long. It is called
from the extraction pipeline, where a failed notification must cost the task
nothing: the task is the product, the push is the courtesy. Same contract as
``campuscue.api.events.hub``.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
from dataclasses import dataclass, field
from xml.sax.saxutils import escape as xml_escape

from astrbot.core import logger
from campuscue import store
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.models import CampusTask, as_utc

# --- settings keys ---------------------------------------------------------
# Stored in campus_settings (see campuscue/models.py:CampusSetting) rather than
# on CampusProfile, which is per-umo.

KEY_TARGET = "notify.target_umo"
KEY_ON_DETECT = "notify.on_detect"
KEY_TOAST = "notify.desktop_toast"
KEY_DEADLINE = "notify.deadline_reminders"

DEFAULT_ON_DETECT = True
DEFAULT_TOAST = True
DEFAULT_DEADLINE = True


def _flag(value: object, default: bool) -> bool:
    """Coerce a stored setting to a bool, tolerating string values.

    The settings column is user-editable JSON; a hand-written "false" is a
    string, and ``bool("false")`` would enable the very switch the value says
    to disable. Missing or unrecognised values keep the default instead of
    flipping it.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        if not text:
            return default
        if text in ("1", "true", "yes", "on", "是"):
            return True
        if text in ("0", "false", "no", "off", "否"):
            return False
        return default
    return default


@dataclass
class NotifySettings:
    """The four switches, resolved. ``target_umo`` empty means "not chosen yet"."""

    target_umo: str = ""
    on_detect: bool = DEFAULT_ON_DETECT
    desktop_toast: bool = DEFAULT_TOAST
    deadline_reminders: bool = DEFAULT_DEADLINE


async def get_settings() -> NotifySettings:
    """Read the notification settings, falling back to the defaults per key."""
    try:
        target = await store.get_setting(KEY_TARGET, "")
        on_detect = await store.get_setting(KEY_ON_DETECT, DEFAULT_ON_DETECT)
        toast_on = await store.get_setting(KEY_TOAST, DEFAULT_TOAST)
        deadline = await store.get_setting(KEY_DEADLINE, DEFAULT_DEADLINE)
    except Exception:  # noqa: BLE001 - a missing table must not stop extraction
        logger.debug("[campuscue] could not read notify settings", exc_info=True)
        return NotifySettings()
    return NotifySettings(
        target_umo=str(target or ""),
        on_detect=_flag(on_detect, DEFAULT_ON_DETECT),
        desktop_toast=_flag(toast_on, DEFAULT_TOAST),
        deadline_reminders=_flag(deadline, DEFAULT_DEADLINE),
    )


async def save_settings(
    *,
    target_umo: str | None = None,
    on_detect: bool | None = None,
    desktop_toast: bool | None = None,
    deadline_reminders: bool | None = None,
) -> NotifySettings:
    """Write only the keys that were passed, then read the whole set back."""
    if target_umo is not None:
        await store.set_setting(KEY_TARGET, target_umo.strip())
    if on_detect is not None:
        await store.set_setting(KEY_ON_DETECT, bool(on_detect))
    if desktop_toast is not None:
        await store.set_setting(KEY_TOAST, bool(desktop_toast))
    if deadline_reminders is not None:
        await store.set_setting(KEY_DEADLINE, bool(deadline_reminders))
    return await get_settings()


async def resolve_target(fallback: str = "") -> str:
    """The umo every push should go to.

    Falls back to the caller's suggestion (normally the task's own origin) when no
    target has been designated, so a fresh install still delivers somewhere
    instead of going quiet -- the settings panel is the fix, not a precondition.
    """
    settings = await get_settings()
    return settings.target_umo or fallback


# --- message text ----------------------------------------------------------


def _deadline_line(task: CampusTask) -> str | None:
    deadline = as_utc(task.deadline)
    if deadline is None:
        return "截止时间：原文没说清，已存为待确认"
    local = deadline.astimezone(CAMPUS_TZ)
    stamp = local.strftime("%m-%d %H:%M")
    if not task.deadline_is_explicit:
        stamp += "（推断）"
    return f"截止 {stamp}"


TYPE_LABELS = {
    "homework": "作业",
    "exam": "考试",
    "competition": "比赛",
    "activity": "活动",
    "notice": "通知",
}


def compose_detection(task: CampusTask) -> str:
    """The detection-time push text.

    Leads with what happened rather than with the task title: this message
    arrives unprompted, so the first line has to explain why the student's phone
    just buzzed. The original message goes in verbatim at the end -- the whole
    trust argument of the product is that the student can always see what the
    model was actually looking at.
    """
    kind = TYPE_LABELS.get(task.task_type, "事务")
    lines = [f"🔍 课讯 · 探测到有用信息（{kind}）", task.title]

    line = _deadline_line(task)
    if line:
        lines.append(line)
    if task.location:
        lines.append(f"📍 {task.location}")
    items = list(task.items or [])
    if items:
        lines.append(f"🎒 需带：{'、'.join(str(i) for i in items)}")

    origin = " · ".join(
        part for part in (task.source_group_name, task.source_sender_name) if part
    )
    if origin:
        lines.append(f"来源 {origin}")
    if task.raw_text:
        raw = task.raw_text.strip().replace("\n", " ")
        if len(raw) > 120:
            raw = raw[:120] + "…"
        lines.append(f"原文「{raw}」")
    if task.status == "pending_confirm":
        lines.append("（置信度不高，已放进待确认，去看板确认一下）")
    return "\n".join(lines)


def toast_lines(task: CampusTask) -> tuple[str, str]:
    """Title and body for the desktop toast. Two short lines, no provenance --
    a toast is a glance, and the detail is one click away in the pushed message."""
    kind = TYPE_LABELS.get(task.task_type, "事务")
    body = task.title
    line = _deadline_line(task)
    if line:
        body = f"{body} · {line}"
    return f"课讯 · 探测到{kind}信息", body


# --- desktop toast ---------------------------------------------------------
# Windows only, no new dependency. The script is fed to PowerShell on stdin
# rather than written to a .ps1 and run with -File, because running a file needs
# -ExecutionPolicy Bypass and weakening a security control to show a notification
# is not a trade worth making. The three WinRT type loads have to happen in a
# script body: as a single -Command string PowerShell resolves the type literals
# before the loads run and New-Object cannot find XmlDocument.

_TOAST_SCRIPT = """
$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom, ContentType=WindowsRuntime] > $null
$doc = New-Object Windows.Data.Xml.Dom.XmlDocument
$doc.LoadXml($env:CAMPUSCUE_TOAST_XML)
$toast = New-Object Windows.UI.Notifications.ToastNotification $doc
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:CAMPUSCUE_TOAST_AUMID).Show($toast)
Write-Output SHOWN
"""

TOAST_AUMID = os.environ.get(
    "CAMPUSCUE_TOAST_AUMID",
    r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe",
)
"""Which installed app the toast is attributed to. Windows refuses to show a
toast from an AUMID with no Start-menu entry, and PowerShell's own is the one
identity guaranteed to exist on a machine that can run this at all."""

TOAST_TIMEOUT = 20.0


def _toast_xml(title: str, body: str) -> str:
    return (
        "<toast><visual><binding template='ToastGeneric'>"
        f"<text>{xml_escape(title)}</text>"
        f"<text>{xml_escape(body)}</text>"
        "</binding></visual></toast>"
    )


def _show_toast_blocking(title: str, body: str) -> bool:
    """Run PowerShell and return whether it reported the toast as shown.

    The payload travels in environment variables, not on the command line: the
    console codepage on a Chinese Windows install is CP936, and a UTF-8 argv turns
    every Chinese character in the task title into mojibake by the time PowerShell
    parses it. Environment variables are handed over as UTF-16 by the OS and
    survive intact.
    """
    if os.name != "nt":
        return False
    env = dict(
        os.environ,
        CAMPUSCUE_TOAST_XML=_toast_xml(title, body),
        CAMPUSCUE_TOAST_AUMID=TOAST_AUMID,
    )
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "-"],
            input=_TOAST_SCRIPT.encode("utf-8"),
            capture_output=True,
            env=env,
            timeout=TOAST_TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("[campuscue] toast failed to launch: %s", exc)
        return False

    if proc.returncode != 0 or b"SHOWN" not in proc.stdout:
        logger.debug(
            "[campuscue] toast not shown (rc=%s): %s",
            proc.returncode,
            proc.stderr.decode("utf-8", "replace").strip()[:200],
        )
        return False
    return True


async def show_toast(title: str, body: str) -> bool:
    """Show a desktop toast. Never raises; returns whether it appeared.

    Off the event loop in a worker thread: spawning PowerShell costs a few hundred
    milliseconds and the extraction pipeline has other messages waiting.
    """
    try:
        return await asyncio.to_thread(_show_toast_blocking, title, body)
    except Exception:  # noqa: BLE001 - a notification is never worth an exception
        logger.debug("[campuscue] toast crashed", exc_info=True)
        return False


# --- the one entry point the pipeline calls --------------------------------


@dataclass
class DeliveryReport:
    """What actually happened, so callers can log the truth instead of "sent"."""

    target: str = ""
    pushed: bool = False
    toasted: bool = False
    skipped: str = ""
    """Why nothing was sent: disabled | no_target | no_context."""
    errors: list[str] = field(default_factory=list)


async def announce_detection(task: CampusTask) -> DeliveryReport:
    """Tell the student, right now, that something useful was found.

    Called from the extraction pipeline immediately after the task is stored.
    Returns a report rather than raising, and treats "no platform matched" as a
    normal outcome -- during a replay demo there is no QQ account attached and the
    board is still the real destination.
    """
    settings = await get_settings()
    if not settings.on_detect:
        return DeliveryReport(skipped="disabled")

    report = DeliveryReport(target=settings.target_umo or task.umo)

    if settings.desktop_toast:
        title, body = toast_lines(task)
        report.toasted = await show_toast(title, body)

    # Imported here, not at module import: reminders holds the star's context and
    # importing it eagerly would make store/notify depend on the framework being up.
    from campuscue import reminders

    context = reminders.push_context()
    if context is None:
        report.skipped = "no_context"
        return report

    from astrbot.core.message.message_event_result import MessageChain

    try:
        report.pushed = bool(
            await context.send_message(
                report.target, MessageChain().message(compose_detection(task))
            )
        )
    except Exception as exc:  # noqa: BLE001 - a dead platform must not lose the task
        logger.exception("[campuscue] detection push failed for task %s", task.task_id)
        report.errors.append(repr(exc))

    if not report.pushed and not report.errors:
        logger.info(
            "[campuscue] no platform available; task %s was not pushed",
            task.task_id,
        )
    return report


__all__ = [
    "DeliveryReport",
    "KEY_DEADLINE",
    "KEY_ON_DETECT",
    "KEY_TARGET",
    "KEY_TOAST",
    "NotifySettings",
    "TOAST_AUMID",
    "announce_detection",
    "compose_detection",
    "get_settings",
    "resolve_target",
    "save_settings",
    "show_toast",
    "toast_lines",
]
