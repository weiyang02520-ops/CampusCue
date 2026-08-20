"""OneBotAdapter - Reverse WebSocket SERVER (NapCat is the CLIENT).

Responsibilities:
- listen for NapCat reverse WS connections (host/port/path configurable)
- accept a single ACTIVE connection; a new connection replaces the old (stale)
- frame classification: Event Frame / Action Response Frame / ignored meta / unknown
- converter: Event Frame -> CampusEvent (pure)
- canonical ingress pipeline: self-suppression -> transport dedup -> bus.publish
- outbound actions with echo correlation; pending futures belong to the connection
  (disconnect/replacement fails that connection's pending actions immediately)
- access token + path validation at handshake (never logs secrets)
- bounded outbound concurrency via semaphore (backpressure, not error)

Key races handled (M1.1 review):
- stale connection's delayed finally never fails the new connection's pending
  actions: pending map is replaced per-connection, and the finally only acts on
  the connection that still owns the active slot
- action response arriving before pending registration (register before send)
- unknown / duplicate echoes (safe ignore)
- cancellation safety: semaphore slots always released
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
from typing import Any

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request

from campuscue.adapters.base import PlatformAdapter
from campuscue.adapters.onebot.converter import (
    ACTION_RESPONSE,
    EVENT,
    IGNORED_META,
    UNKNOWN,
    ValidationError,
    classify_frame,
    convert_message,
)
from campuscue.adapters.onebot.dedup import TransportDedup
from campuscue.adapters.onebot.protocol import (
    ActionError,
    build_action,
    new_echo,
    validate_response,
)
from campuscue.config import OneBotConfig
from campuscue.core.events import CampusEvent, ConversationType
from campuscue.core.outbound import OutgoingMessage

logger = logging.getLogger("campuscue.onebot")


class ActionFailure(Exception):
    """Outbound action did not succeed. Message is safe to log (no raw payload)."""


class OneBotAdapter(PlatformAdapter):
    def __init__(self, config: OneBotConfig, *, on_event, on_connection=None) -> None:
        self._config = config
        self._on_event = on_event  # awaitable(CampusEvent) -> None (bus.publish)
        self._on_connection = on_connection  # awaitable(bool) -> None; optional neutral notifier boundary
        self._server = None
        self._server_task: asyncio.Task[None] | None = None
        self._conn: ServerConnection | None = None
        # pending futures belong to the CURRENT connection generation; replaced
        # on connect/disconnect/replacement so a stale cleanup can never fail a
        # new connection's actions (M1.1 finding A)
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._pending_sem = asyncio.Semaphore(config.max_pending_actions)
        self._send_lock = asyncio.Lock()
        self._dedup = TransportDedup(ttl_s=config.dedup_ttl_s, capacity=config.dedup_capacity)
        self._started = False
        self._stopping = False

    # ------------------------------------------------------------------ lifecycle

    async def start(self) -> None:
        cfg = self._config
        if cfg.host not in ("127.0.0.1", "localhost", "::1"):
            raise RuntimeError(
                f"OneBot host {cfg.host!r} is not loopback; LAN exposure requires explicit "
                "opt-in plus an access token (not implemented in M1). Refusing to start."
            )
        self._server = await serve(
            self._handle_connection, cfg.host, cfg.port, process_request=self._check_handshake
        )
        self._server_task = asyncio.create_task(self._server.serve_forever(), name="onebot.server")
        self._started = True
        logger.info("onebot reverse ws server listening on ws://%s:%s%s", cfg.host, cfg.port, cfg.path)

    async def stop(self) -> None:
        self._stopping = True
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        self._fail_all_pending("adapter stopped")
        if self._server is not None:
            self._server.close()
            if self._server_task is not None:
                try:
                    await asyncio.wait_for(self._server_task, 3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._server_task.cancel()
                self._server_task = None
        self._started = False
        logger.info("onebot adapter stopped")

    # ------------------------------------------------------------------ inbound

    async def _check_handshake(self, connection: ServerConnection, request: Request):
        """Validate path first, then access token (if configured). Never logs secrets."""
        if request.path != self._config.path:
            logger.warning("onebot ws handshake rejected: wrong path")
            return connection.respond(404, "Not Found")
        if self._config.access_token:
            header = request.headers.get("Authorization", "")
            expected = f"Bearer {self._config.access_token}"
            if not hmac.compare_digest(header, expected):
                logger.warning("onebot ws handshake rejected: missing/invalid access token")
                return connection.respond(401, "Unauthorized")
        return None  # allow handshake

    async def _handle_connection(self, conn: ServerConnection) -> None:
        if self._stopping:
            await conn.close()
            return
        # new connection wins: replace the active slot, own a fresh pending map
        old = self._conn
        self._conn = conn
        if old is not None and old is not conn:
            old_pending = self._pending
            self._pending = {}
            # fail the OLD connection's pending actions; the new connection gets
            # a fresh map so a delayed old cleanup can never touch its futures
            self._fail_pending(old_pending, "connection replaced by new connection")
            await self._notify_connection(False)
            try:
                await old.close()
            except Exception:
                pass
        logger.info("onebot client connected")
        await self._notify_connection(True)
        try:
            async for raw in conn:
                if self._conn is not conn:
                    break  # superseded; do not process frames for a stale connection
                await self._on_frame(raw)
        except ConnectionClosed:
            pass
        except Exception:
            logger.exception("onebot connection loop error")
        finally:
            if self._conn is conn:
                # we still own the active slot: this is a genuine disconnect
                self._conn = None
                self._fail_all_pending("connection lost")
                await self._notify_connection(False)
            # else: superseded — pending map already belongs to the new connection
            logger.info("onebot client disconnected")

    async def _on_frame(self, raw: Any) -> None:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("onebot invalid frame: not JSON")
            return
        kind = classify_frame(payload)
        if kind == ACTION_RESPONSE:
            self._resolve_action_response(payload)
            return
        if kind == IGNORED_META:
            return  # lifecycle / heartbeat / notice / request: safe ignore
        if kind == UNKNOWN:
            logger.debug("onebot unknown frame type")
            return
        # EVENT frame
        try:
            event = convert_message(payload, adapter_id=self._config_id)
        except ValidationError as e:
            logger.warning("onebot message invalid: %s", e)
            return
        # canonical ingress pipeline (transport dedup exactly once)
        if event.sender_id == event.self_id:
            return  # self-message suppression (canonical point)
        if not self._dedup.check_and_add(event.self_id, event.message_id):
            logger.debug("onebot duplicate delivery suppressed trace=%s", event.trace_id[:8])
            return
        await self._on_event(event)

    @property
    def _config_id(self) -> str:
        return f"onebot:{self._config.host}:{self._config.port}"

    # ------------------------------------------------------------------ outbound

    async def _notify_connection(self, connected: bool) -> None:
        if self._on_connection is None:
            return
        try:
            await self._on_connection(connected)
        except Exception:
            # Realtime is derived notification; a notifier failure must not
            # break the adapter connection lifecycle.
            logger.exception("connection lifecycle notification failed")

    async def send(self, message: OutgoingMessage) -> None:
        if message.conversation_type == ConversationType.GROUP:
            action, params = "send_group_msg", {"group_id": int(message.conversation_id), "message": message.text}
        elif message.conversation_type == ConversationType.PRIVATE:
            action, params = "send_private_msg", {"user_id": int(message.conversation_id), "message": message.text}
        else:
            raise ActionFailure(f"unsupported conversation_type {message.conversation_type!r}")
        await self._send_action(action, params)

    async def _send_action(self, action: str, params: dict[str, Any]) -> None:
        """Send one action with echo correlation.

        Bounded by a semaphore: when max_pending_actions is reached, callers
        WAIT for a free slot (backpressure), they never get an immediate error
        (M1.1 finding C). The semaphore is released in a finally block so a
        cancelled task can never leak a slot.
        """
        await self._pending_sem.acquire()
        try:
            conn = self._conn
            if conn is None:
                raise ActionFailure("no active connection")
            echo = new_echo()
            fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            # register BEFORE send to avoid response-before-registration race
            self._pending[echo] = fut
            frame = json.dumps(build_action(action, params, echo))
            try:
                async with self._send_lock:
                    await conn.send(frame)
                try:
                    response = await asyncio.wait_for(fut, self._config.action_timeout_s)
                except asyncio.TimeoutError:
                    self._pending.pop(echo, None)
                    raise ActionFailure(f"action {action} timed out")
            except ConnectionClosed:
                self._pending.pop(echo, None)
                raise ActionFailure("connection closed while sending action")
            finally:
                self._pending.pop(echo, None)
            try:
                validate_response(response)
            except ActionError as e:
                raise ActionFailure(f"{e.message} (retcode={e.retcode})") from e
        finally:
            self._pending_sem.release()

    def _resolve_action_response(self, payload: dict[str, Any]) -> None:
        echo = payload.get("echo")
        if not isinstance(echo, str):
            return
        fut = self._pending.get(echo)
        if fut is None or fut.done():
            logger.debug("onebot unknown/duplicate echo ignored")
            return
        fut.set_result(payload)

    def _fail_all_pending(self, reason: str) -> None:
        self._fail_pending(self._pending, reason)
        self._pending = {}

    def _fail_pending(self, pending: dict[str, asyncio.Future[dict[str, Any]]], reason: str) -> None:
        for fut in pending.values():
            if not fut.done():
                fut.set_exception(ActionFailure(reason))

    # ------------------------------------------------------------------ status

    def status(self) -> dict:
        return {
            "adapter_id": self._config_id,
            "listening": self._started,
            "connected": self._conn is not None,
            "pending_actions": len(self._pending),
            "dedup_entries": len(self._dedup),
        }
