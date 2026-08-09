"""课讯 CampusCue - the observer that makes the bot proactive.

Why this exists
---------------
AstrBot only processes a group message when the bot is woken: mentioned, replied
to, or prefixed with a wake word. ``WakingCheckStage`` ends with

    if not is_wake:
        event.stop_event()

so every ordinary group message is dropped at the first stage. But a teacher
posting "实验三报告周五晚上12点前提交" never @s the bot -- which means the
messages CampusCue exists to read are exactly the ones the framework throws
away.

This handler is the bypass. Registering an ``AdapterMessageEvent`` handler with
an ``event_message_type`` filter makes ``WakingCheckStage`` treat the event as
activated, so it survives to ``StarRequestSubStage`` and reaches us.

The dangerous part, and why the guard below matters
--------------------------------------------------
``WakingCheckStage`` sets ``is_wake = True`` when a plugin filter passes, but it
does NOT set ``is_at_or_wake_command`` -- that flag is only set when the user
really did mention the bot or use a wake prefix. ``ProcessStage`` gates the
default LLM reply on

    if not event._has_send_oper and event.is_at_or_wake_command and not event.call_llm

so an observer that never sends anything leaves the bot silent. That is the
behaviour we depend on, and ``test_bypass.py`` asserts it rather than trusting
this comment: if a future upstream change starts replying to every group
message, the test fails instead of the demo.

Consequences for this handler:
  * never ``yield`` a result, never call ``event.send()``
  * never call ``event.stop_event()`` -- stopping the event would also cancel
    the normal @-mention conversation for messages that legitimately woke the bot
  * never block: extraction talks to an LLM and takes seconds, so the work is
    handed to a background task and the pipeline continues immediately
"""

import asyncio
from datetime import datetime, timezone

import httpx

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from campuscue import reminders
from campuscue.extractor.prompt import WEEKDAY_CN
from campuscue.extractor.timeresolve import CAMPUS_TZ
from campuscue.persona import build_time_hint


class CampusCue(Star):
    """Observes group messages and hands them to the extraction pipeline."""

    def __init__(self, context: Context) -> None:
        super().__init__(context)
        # Strong references to in-flight extraction tasks. asyncio only keeps a
        # weak reference to a running task, so without this set a task can be
        # garbage collected mid-await. astrbot.core.event_bus keeps its own
        # _pending_tasks set for the same reason.
        self._pending: set[asyncio.Task] = set()
        # Extraction is I/O bound on the LLM. The bound stops a burst of group
        # traffic from opening hundreds of concurrent requests.
        self._slots = asyncio.Semaphore(4)
        self._seen = 0
        self._observed = 0
        # One pooled client for the process. Opening a connection per message
        # would add a TLS handshake to every extraction.
        self._client: httpx.AsyncClient | None = None
        self._load_env()
        self._register_tools()

    @staticmethod
    def _load_env() -> None:
        """Put ``.env`` into the process environment before providers load.

        astrbot has no dotenv step, and the DeepSeek provider's key is stored in
        config as the literal ``$DEEPSEEK_API_KEY`` for
        ``ProviderManager._resolve_env_key_list`` to expand. Without this the
        expansion finds nothing, the OpenAI client raises "Missing credentials",
        and the bot boots with no conversational model at all -- reminders and
        extraction still work, so the failure is quiet.

        Here rather than in main.py because the ordering is what makes it
        correct: ``plugin_manager.reload()`` instantiates stars at
        core_lifecycle.py:246, ``provider_manager.initialize()`` runs at :250. It
        also keeps the fork's edits inside CampusCue's own files.
        """
        from campuscue.extractor.llm import load_env_file

        load_env_file()

    def _register_tools(self) -> None:
        """Give the main agent the campus toolset.

        Done in ``__init__`` rather than at import time so the tools appear in
        exactly the sessions where this star is loaded, and via
        ``Context.add_llm_tools`` rather than the ``@builtin_tool`` registry --
        that registry's module list is inside ``astrbot/`` and extending it would
        add a fourth intrusion into the base for no functional gain.

        Failure is logged, not raised: without the tools CampusCue still reads
        the group and pushes reminders, which is the majority of the product. A
        star that refuses to load would lose that too.
        """
        try:
            from campuscue.tools import build_tools

            tools = build_tools()
            self.context.add_llm_tools(*tools)
            logger.info(
                "[campuscue] registered %d tools: %s",
                len(tools),
                ", ".join(t.name for t in tools),
            )
        except Exception:  # noqa: BLE001
            logger.exception("[campuscue] could not register tools")

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient()
        return self._client

    @filter.on_llm_request()
    async def inject_now(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        """Tell the agent what day it is, every request.

        Nothing in astrbot puts the current time into a system prompt, and the
        campus tools refuse a relative deadline rather than guessing at one
        (campuscue/tools.py ``_parse_when``). So without this line a student
        saying "下周五交" gets either an error or a date the model invented from
        its training cutoff -- and a wrong deadline is the one failure this
        product cannot have.

        Appended per request rather than baked into the stored persona because a
        persona row is written once and the answer changes every minute.
        """
        now = datetime.now(CAMPUS_TZ)
        req.system_prompt = (req.system_prompt or "") + build_time_hint(
            now, WEEKDAY_CN[now.weekday()]
        )

    @filter.on_astrbot_loaded()
    async def bind_scheduler(self) -> None:
        """Hand the scheduler and push channel to the reminder module.

        Deferred to this hook rather than done in ``__init__``: stars are
        instantiated before ``cron_manager.start()`` runs
        (astrbot/core/core_lifecycle.py), so binding earlier would capture a
        scheduler that has not been started and cannot accept jobs.

        The resync afterwards rebuilds the schedule from the tasks themselves --
        see campuscue/reminders.py on why the cron table is treated as a cache.
        It runs detached because a slow reconcile must not hold up startup.
        """
        reminders.bind(self.context.cron_manager, self.context)
        if self.context.cron_manager is None:
            logger.warning("[campuscue] no cron manager, reminders are disabled")
            return

        task = asyncio.create_task(self._resync())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _resync(self) -> None:
        try:
            await reminders.resync_all()
        except Exception:  # noqa: BLE001 - startup must survive a bad row
            logger.exception("[campuscue] reminder resync failed")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def observe_group_message(self, event: AstrMessageEvent):
        """Tee every group message into the campus extraction pipeline.

        Deliberately returns nothing. See the module docstring: yielding a
        result here would make the bot answer every message in the group.
        """
        self._seen += 1
        text = (event.message_str or "").strip()
        if not text:
            return

        # Ignore the bot's own messages, otherwise a reminder push could be
        # re-extracted into a new task.
        if event.get_self_id() and event.get_self_id() == event.get_sender_id():
            return

        self._observed += 1
        logger.debug(
            "[campuscue] observed #%d (chars=%d)",
            self._observed,
            len(text),
        )

        task = asyncio.create_task(self._extract(event, text))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _extract(self, event: AstrMessageEvent, text: str) -> None:
        """Run the extraction pipeline for one message, off the hot path."""
        # Imported lazily so the star module can be imported (and unit-tested)
        # without pulling in the database and HTTP layers.
        from campuscue.extractor.pipeline import MessageContext, process_message

        async with self._slots:
            try:
                sent_at = self._sent_at(event)
                ctx = MessageContext(
                    umo=event.unified_msg_origin,
                    text=text,
                    sent_at=sent_at,
                    message_id=str(event.message_obj.message_id or "") or None,
                    sender_id=str(event.get_sender_id() or "") or None,
                    sender_name=event.get_sender_name() or None,
                    sender_role=self._sender_role(event),
                    group_name=self._group_name(event),
                )
                # process_message never raises; it records its own failures as
                # audit rows so the trace stays honest.
                await process_message(ctx, client=self._http())
            except Exception:  # noqa: BLE001 - a bad message must not kill the loop
                logger.exception(
                    "[campuscue] extraction failed (message_id=%s, chars=%d)",
                    getattr(event.message_obj, "message_id", None),
                    len(text),
                )

    @staticmethod
    def _sender_role(event: AstrMessageEvent) -> str | None:
        """The platform's own role for the sender: owner / admin / member.

        OneBot puts it in the raw group message under ``sender.role``, which the
        aiocqhttp adapter keeps on ``message_obj.raw_message``. Reading it here
        means a teacher who is the group owner is treated as authoritative
        without anyone filling in ``authority_senders`` first -- see
        campuscue/extractor/pipeline.py:AUTHORITY_ROLES.

        Returns None on any platform that does not expose roles; the pipeline
        then falls back to the configured list.
        """
        raw = getattr(event.message_obj, "raw_message", None)
        sender = getattr(raw, "sender", None)
        if sender is None and isinstance(raw, dict):
            sender = raw.get("sender")
        if isinstance(sender, dict):
            role = sender.get("role")
            if isinstance(role, str) and role:
                return role
        return None

    @staticmethod
    def _group_name(event: AstrMessageEvent) -> str | None:
        """The group's display name, not its numeric id.

        ``get_group_id()`` returns the numeric QQ group number, which the
        pipeline would otherwise show the model as "群名称：12345678" and print
        on every task card -- hiding the display name the student configured on
        the board. The adapter keeps the real name on ``message_obj.group``;
        OneBot v11 does not always include it in a message event, so fall back
        to None and let the pipeline use ``source.display_name`` instead.
        """
        group = getattr(event.message_obj, "group", None)
        name = getattr(group, "group_name", None) if group is not None else None
        if isinstance(name, str) and name.strip() and name != "N/A":
            return name.strip()
        return None

    @staticmethod
    def _sent_at(event: AstrMessageEvent) -> datetime:
        """When the message was sent, as timezone-aware UTC.

        This is the anchor L3 resolves "周五" against, so using the extraction
        time instead would silently shift deadlines for any message that sat in a
        queue. Platform timestamps are Unix seconds; fall back to now when a
        platform omits it.

        The aiocqhttp adapter overwrites ``message_obj.timestamp`` with
        ``time.time()`` at processing time (aiocqhttp_platform_adapter.py:421),
        so the real send time lives on the raw OneBot payload's ``time`` field.
        Read that first, then the adapter's timestamp.
        """
        raw = getattr(event.message_obj, "raw_message", None)
        if isinstance(raw, dict):
            raw_time = raw.get("time")
            if raw_time:
                try:
                    return datetime.fromtimestamp(float(raw_time), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    logger.debug("[campuscue] unusable raw time %r", raw_time)
        raw = getattr(event.message_obj, "timestamp", None)
        if raw:
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (TypeError, ValueError, OSError):
                logger.debug("[campuscue] unusable timestamp %r", raw)
        return datetime.now(timezone.utc)

    async def terminate(self) -> None:
        reminders.bind(None, None)
        for task in list(self._pending):
            task.cancel()
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        logger.info(
            "[campuscue] stopped. group messages seen=%d observed=%d",
            self._seen,
            self._observed,
        )
