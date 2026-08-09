"""The 接入与自检 page's backend: bring CampusCue online without a terminal.

Everything here exists to collapse a setup checklist into buttons. The student's
only irreducible step is a scan on their phone; the rest -- install NapCat, point
it at our reverse-WebSocket port, start it, notice the socket came up, read which
groups the account is in, choose which of them to watch, prove a reminder can be
delivered -- has one correct answer per step, and this module knows all of them.

Two design decisions worth stating:

* **Status is one document, not five endpoints.** The page polls while someone
  watches it. Separate polls let the sections disagree mid-scan, and a QR panel
  reading 未连接 beside a group list reading 已连接 is worse than a slower
  refresh.
* **Link state comes from the adapter, not from NapCat.** A correct config file
  proves nothing; an open reverse-WS client proves the entire chain, and the
  handshake carries the uin, so the logged-in account is known without asking
  NapCat's webui anything.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query

from astrbot.core import logger
from campuscue import napcat, store
from campuscue.api.events import hub
from campuscue.api.routes import _maybe_require_auth
from campuscue.api.schemas import (
    CheckOut,
    LinkOut,
    NapCatLogOut,
    NapCatOut,
    SetupActionOut,
    SetupStatusOut,
    SourceOut,
    short_umo,
)

router = APIRouter(prefix="/campus/setup", tags=["CampusCue Setup"])


def _napcat_out(state: napcat.State) -> NapCatOut:
    return NapCatOut(
        installed=state.installed,
        home=state.home,
        running=state.running,
        pid=state.pid,
        managed=state.managed,
        configured=state.configured,
        ws_url=state.ws_url,
        installing=state.installing,
        supported=state.supported,
        detail=state.detail,
        accounts=state.accounts,
    )


def _qq_adapter():
    """The live aiocqhttp adapter instance, or None.

    Reached through the bound reminder context because that is the only handle
    campuscue keeps on the running core; an HTTP request has no other route to
    the platform manager.
    """
    from campuscue import reminders as rem

    if rem._ctx is None:
        return None
    for platform in rem._ctx.platform_manager.platform_insts:
        if platform.meta().name == "aiocqhttp":
            return platform
    return None


def link_state() -> LinkOut:
    """Whether a QQ account is attached right now.

    ``_wsr_api_clients`` is keyed by self-id, which is the account's uin -- so
    the same read that proves the socket is open also says who logged in. It is
    aiocqhttp-internal, and deliberately used anyway: the alternative is polling
    NapCat's webui for a claim about its own state, when the socket into this
    process is the ground truth about whether messages can actually arrive.
    """
    port = int(os.environ.get("CAMPUSCUE_ONEBOT_PORT", "6199"))
    adapter = _qq_adapter()
    if adapter is None:
        return LinkOut(
            adapter_ready=False,
            port=port,
            detail="QQ 适配器未加载（先跑一次 provision，再重启）",
        )

    try:
        bot = adapter.get_client()
        accounts = sorted(str(k) for k in getattr(bot, "_wsr_api_clients", {}))
    except Exception as exc:  # noqa: BLE001 - a status page must not 500
        logger.warning(f"[CampusCue] 读取 NapCat 连接状态失败: {exc}")
        return LinkOut(adapter_ready=True, port=port, detail=repr(exc))

    return LinkOut(
        adapter_ready=True,
        connected=bool(accounts),
        accounts=accounts,
        port=port,
        detail=f"已连接 QQ {'/'.join(accounts)}" if accounts else "等待 NapCat 连接",
    )


@router.get("/status", response_model=SetupStatusOut)
async def status(_: None = Depends(_maybe_require_auth)) -> SetupStatusOut:
    """One read of everything the page shows."""
    from campuscue import provision
    from campuscue import reminders as rem

    try:
        raw_checks = await provision.collect_checks()
    except Exception as exc:  # noqa: BLE001
        logger.exception("[campuscue] self-check failed")
        raw_checks = [("自检", False, f"自检本身出错：{exc}")]

    checks = [CheckOut(group=g, ok=ok, text=t) for g, ok, t in raw_checks]

    counts = await store.count_tasks_by_umo()
    sources = [
        SourceOut.of(source, counts.get(source.umo, 0))
        for source in await store.list_sources()
    ]

    return SetupStatusOut(
        checks=checks,
        problems=sum(1 for c in checks if not c.ok),
        napcat=_napcat_out(napcat.status()),
        link=link_state(),
        sources=sources,
        scheduler_ready=rem.is_bound(),
        # The L2 call reads these env vars at request time (extractor/llm.py);
        # the key *and* the model id must both be present or extraction cannot
        # start, so both are checked here.
        extractor_ready=bool(os.environ.get("ARK_API_KEY"))
        and bool(os.environ.get("ARK_EXTRACT_MODEL") or os.environ.get("ARK_MODEL")),
    )


# --- NapCat lifecycle ----------------------------------------------------


@router.post("/napcat/install", response_model=SetupActionOut)
async def install_napcat(_: None = Depends(_maybe_require_auth)) -> SetupActionOut:
    """Download and unpack NapCat Shell.

    Runs inline rather than as a background task: ~30MB off GitHub takes long
    enough that the page has to show progress anyway, and a fire-and-forget task
    whose failure only lands in the log is exactly the opaque setup step this
    page exists to remove. The request just takes a while.
    """
    try:
        home = await napcat.install()
    except napcat.NapCatError as exc:
        return SetupActionOut(
            ok=False, detail=str(exc), napcat=_napcat_out(napcat.status())
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("[campuscue] NapCat install failed")
        return SetupActionOut(
            ok=False, detail=f"安装失败：{exc}", napcat=_napcat_out(napcat.status())
        )
    return SetupActionOut(
        ok=True, detail=f"已安装到 {home}", napcat=_napcat_out(napcat.status())
    )


@router.post("/napcat/start", response_model=SetupActionOut)
async def start_napcat(_: None = Depends(_maybe_require_auth)) -> SetupActionOut:
    """Write the reverse-WS config and launch NapCat, so the QR appears."""
    try:
        pid = napcat.start()
    except napcat.NapCatError as exc:
        return SetupActionOut(
            ok=False, detail=str(exc), napcat=_napcat_out(napcat.status())
        )
    return SetupActionOut(
        ok=True,
        detail=f"已启动（pid {pid}），扫码后自动连接",
        napcat=_napcat_out(napcat.status()),
    )


@router.post("/napcat/stop", response_model=SetupActionOut)
async def stop_napcat(_: None = Depends(_maybe_require_auth)) -> SetupActionOut:
    """Stop only the NapCat this process started.

    A NapCat the student launched themselves is theirs, and stopping by image
    name would take their QQ client down with it.
    """
    stopped = napcat.stop()
    return SetupActionOut(
        ok=True,
        detail="已停止" if stopped else "没有由本程序启动的 NapCat",
        napcat=_napcat_out(napcat.status()),
    )


@router.post("/napcat/configure", response_model=SetupActionOut)
async def configure_napcat(_: None = Depends(_maybe_require_auth)) -> SetupActionOut:
    """Repoint every NapCat config at our port.

    Separate from start because the failure it fixes happens after a successful
    start: an account that logged in against an older port keeps its own
    ``onebot11_<uin>.json``, so a restart alone reconnects to nothing.
    """
    home, _launcher = napcat.find_home()
    if home is None:
        return SetupActionOut(ok=False, detail="还没装 NapCat")
    written = napcat.apply_config(home, napcat.ws_url())
    detail = (
        f"已写入 {'、'.join(written)}，重启 NapCat 生效"
        if written
        else "配置已是目标状态"
    )
    return SetupActionOut(ok=True, detail=detail, napcat=_napcat_out(napcat.status()))


@router.get("/napcat/log", response_model=NapCatLogOut)
async def napcat_log(
    lines: int = Query(default=160, ge=10, le=1000),
    _: None = Depends(_maybe_require_auth),
) -> NapCatLogOut:
    """NapCat's console plus the QR sliced out of it, for the scan panel."""
    body = napcat.tail(lines)
    return NapCatLogOut(
        log=body, qrcode=napcat.qrcode_block(body), running=napcat.is_running()
    )


# --- groups --------------------------------------------------------------


@router.post("/groups/sync", response_model=list[SourceOut])
async def sync_groups(_: None = Depends(_maybe_require_auth)) -> list[SourceOut]:
    """Pull the account's joined groups from QQ and register them as sources.

    Without this a group only appears after someone talks in it, which makes the
    watch list unusable at exactly the moment it matters -- right after the scan,
    when a student wants to pick their course groups before a demo.

    New rows are created disabled. Adopting every group an account happens to be
    in would start extracting from private chats and unrelated groups on the
    student's behalf, and the point of this screen is that watching is chosen.
    """
    from campuscue.provision import PLATFORM_ID

    adapter = _qq_adapter()
    if adapter is None:
        raise HTTPException(status_code=409, detail="QQ 适配器未加载")

    link = link_state()
    if not link.connected:
        raise HTTPException(status_code=409, detail="还没有 QQ 连上来，先扫码")

    try:
        groups = await adapter.get_client().call_action("get_group_list")
    except Exception as exc:  # noqa: BLE001
        logger.exception("[campuscue] get_group_list failed")
        raise HTTPException(status_code=502, detail=f"拉取群列表失败：{exc}") from exc

    known = {source.umo: source for source in await store.list_sources()}
    for group in groups or []:
        group_id = str(group.get("group_id") or "").strip()
        if not group_id:
            continue
        umo = f"{PLATFORM_ID}:GroupMessage:{group_id}"
        name = str(group.get("group_name") or "").strip() or None
        if umo in known:
            # Only fill the label when the student has not set one. A name they
            # typed in the board ("软件工程") is theirs; overwriting it with
            # NapCat's current group_name on every resync would make the manual
            # mapping pointless.
            existing = known[umo]
            if name and not (existing.display_name or "").strip():
                await store.update_source(umo, display_name=name)
            continue
        await store.update_source(umo, display_name=name, enabled=False)

    counts = await store.count_tasks_by_umo()
    out = [
        SourceOut.of(source, counts.get(source.umo, 0))
        for source in await store.list_sources()
    ]
    hub.publish("sources_synced", {"count": len(out)})
    return out


@router.post("/groups/{umo:path}/watch", response_model=SourceOut)
async def set_watch(
    umo: str,
    on: bool = Query(default=True),
    _: None = Depends(_maybe_require_auth),
) -> SourceOut:
    """Turn extraction for one group on or off.

    ``{umo:path}`` because a umo contains colons; the default converter would cut
    it at the first one and toggle the wrong group.
    """
    source = await store.update_source(umo, enabled=on)
    counts = await store.count_tasks_by_umo()
    out = SourceOut.of(source, counts.get(umo, 0))
    hub.publish("source_updated", out.model_dump(mode="json"))
    return out


@router.post("/selftest", response_model=SetupActionOut)
async def selftest(
    umo: str = Query(default=None),
    _: None = Depends(_maybe_require_auth),
) -> SetupActionOut:
    """Push one message to the chosen group, end to end.

    The last question the page can answer for a student: not "is it configured"
    but "did a message actually arrive on my phone". Goes through the same
    ``send_message`` the scheduler uses, so a delivered test means a scheduled
    reminder will land too.

    Defaults to a group that is actually being watched, not ``DEFAULT_UMO``. That
    constant is the webchat demo session, so on a machine with a real QQ linked
    the button reported "没有平台匹配 aiocqhttp:GroupMessage:demo-7788" -- a
    failure of the test's own target rather than of the thing being tested, right
    after the student finished connecting. A watched group is the only target
    where "收到了" answers the question the button asks.
    """
    from astrbot.core.message.message_event_result import MessageChain
    from campuscue import reminders as rem
    from campuscue import store
    from campuscue.api.routes import DEFAULT_UMO

    if not rem.is_bound():
        return SetupActionOut(ok=False, detail="调度器未就绪（后端刚启动？稍等再试）")

    if umo:
        targets = [umo]
    else:
        # Every watched group, not just the first. A board that has been tested
        # keeps sources whose platform is long gone (a replay session, a retired
        # adapter), and those sort ahead of the real group by nothing more than
        # insertion order -- so stopping at the first one turns a working push
        # into a failure report.
        targets = [s.umo for s in await store.list_sources() if s.enabled]
        targets.append(DEFAULT_UMO)

    tried: list[str] = []
    for target in targets:
        text = (
            "CampusCue 连通性自检\n"
            f"这条消息发到 {short_umo(target)}。收到说明提醒推送这条链路是通的。"
        )
        try:
            delivered = await rem._ctx.send_message(
                target, MessageChain().message(text)
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[campuscue] setup selftest push failed")
            return SetupActionOut(ok=False, detail=f"推送失败：{exc}")
        if delivered:
            return SetupActionOut(
                ok=True, detail=f"已推送到 {short_umo(target)}，去 QQ 里看一眼"
            )
        tried.append(short_umo(target))

    return SetupActionOut(
        ok=False,
        detail=f"没有平台匹配这些来源：{'、'.join(tried)}。先扫码接入，或勾选一个真实的群。",
    )


__all__ = ["link_state", "router"]
