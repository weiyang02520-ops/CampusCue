"""Bring a fresh checkout to a runnable CampusCue in one command.

    .venv/Scripts/python.exe -m campuscue.provision
    .venv/Scripts/python.exe -m campuscue.provision --check

Why this is a script and not a documented click-path through the WebUI: the
provincial round includes an on-site visit where the project has to start on a
laptop in front of someone. "Open the dashboard, add a provider, paste a key,
pick a persona, save" is five chances to mistype something under pressure. This
does the same five things from ``.env``, idempotently, and ``--check`` reports
what is missing without touching anything.

It writes two files:

* ``data/cmd_config.json`` -- the provider instance, the default provider id,
  the default persona id, and the disabled platform adapters.
* ``data/data_v4.db``     -- the ``personas`` row holding campuscue's prompt.

Both are git-ignored, which is the reason this exists at all: a clone has
neither, so without this module a fresh checkout has no conversational model and
the five campus tools have nobody to call them.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "cmd_config.json"

PROVIDER_ID = "deepseek-chat"
"""Instance id, distinct from the "DeepSeek" template in
astrbot/core/config/default.py. The template is a shape; this is the configured
model the agent actually talks to."""

PROVIDER_SOURCE_ID = f"{PROVIDER_ID}_source"
"""Id of the connection half in ``provider_sources``.

The ``_source`` suffix is not decorative: ``_migra_provider_to_source_structure``
derives exactly this name (``provider["id"] + "_source"``) when it splits a legacy
single-entry provider. Matching it means a config written by provisioning and one
produced by the migration converge instead of accumulating rows."""

PLATFORM_ID = "qq"
"""The OneBot v11 instance id.

Load-bearing, not cosmetic: ``AstrMessageEvent.__init__`` builds the session with
``platform_name=platform_meta.id`` (astr_message_event.py:69), so this string is
the first segment of every umo the QQ path produces -- ``qq:GroupMessage:<group>``.
Renaming it later orphans every task, source row, and reminder already stored
against the old umos, so it is fixed here once and never derived from the
adapter type."""

DEFAULT_WS_PORT = 6199
"""Where NapCat connects back to. Matches the "OneBot v11" template in
astrbot/core/config/default.py so a student who configures it through the WebUI
instead lands on the same port."""

# Every adapter shipped by astrbot except the two CampusCue needs. Disabled
# rather than deleted: the fork stays rebaseable against upstream, and the
# pitch's "we trimmed a general platform down to one domain" is a config diff
# anyone can read. aiocqhttp stays for the real QQ path; webchat is instantiated
# unconditionally by PlatformManager.initialize and needs no entry.
UNUSED_ADAPTERS = (
    "dingtalk",
    "discord",
    "kook",
    "lark",
    "line",
    "mattermost",
    "misskey",
    "qqofficial",
    "qqofficial_webhook",
    "satori",
    "slack",
    "telegram",
    "wecom",
    "wecom_ai_bot",
    "weixin_oc",
    "weixin_official_account",
)


def load_env() -> None:
    from campuscue.extractor.llm import load_env_file

    load_env_file(ROOT)


def read_config() -> dict:
    # utf-8-sig: astrbot writes this file itself and tolerates a BOM on read
    # (astrbot/core/config/astrbot_config.py), so it can be there.
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))


def write_config(conf: dict) -> None:
    # Atomic write, mirroring astrbot's own save path (astrbot_config.py): a
    # crash mid-write must not leave cmd_config.json truncated, because astrbot
    # only rebuilds that file when it is missing, not when it is corrupt.
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix="cmd_config.", suffix=".tmp", dir=str(CONFIG_PATH.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(conf, ensure_ascii=False, indent=4))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, CONFIG_PATH)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def provider_source_entry() -> dict:
    """Connection half of the DeepSeek instance: endpoint, credentials, timeouts.

    astrbot v4.26 split a provider in two -- ``provider_sources`` holds how to
    reach the vendor, ``provider`` holds which model to ask for -- and
    ``get_merged_provider_config`` joins them at load time by
    ``provider_source_id``.

    Provisioning has to write both halves, not the pre-split single entry.
    ``_migra_provider_to_source_structure`` rewrites any provider it finds
    without a ``provider_source_id``, appending a freshly-derived
    ``<id>_source`` -- so a single-entry provisioner and the migration take turns
    undoing each other, and ``provider_sources`` grows by one duplicate row per
    boot. ``dedupe_provider_sources`` cleans that up; writing the right shape
    stops causing it.

    ``key`` holds the literal ``$DEEPSEEK_API_KEY``, not the key itself:
    ``ProviderManager._resolve_env_key_list`` expands a leading ``$`` from the
    environment at load time, so the secret stays in the git-ignored ``.env``
    and this config file remains safe to show on a projector.
    """
    return {
        "id": PROVIDER_SOURCE_ID,
        "provider": "deepseek",
        "type": "openai_chat_completion",
        # Gates env-key expansion (manager.py:591). Checked *after* the merge,
        # so it has to live on this half.
        "provider_type": "chat_completion",
        "key": ["$DEEPSEEK_API_KEY"],
        "api_base": "https://api.deepseek.com/v1",
        "timeout": 120,
        "proxy": "",
        "custom_headers": {},
    }


def provider_entry() -> dict:
    """Model half: which DeepSeek model, and whether it is on.

    Exactly the fields ``_migra_provider_to_source_structure`` leaves behind
    (``provider_only_fields``), so the migration sees nothing to do.
    """
    return {
        "id": PROVIDER_ID,
        "provider_source_id": PROVIDER_SOURCE_ID,
        "enable": True,
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "modalities": [],
        "custom_extra_body": {},
    }


def apply_provider(conf: dict) -> list[str]:
    """Upsert both halves of the provider and make it the default."""
    changed: list[str] = []

    sources = conf.setdefault("provider_sources", [])
    source = provider_source_entry()
    for i, existing in enumerate(sources):
        if existing.get("id") == PROVIDER_SOURCE_ID:
            if existing != source:
                sources[i] = source
                changed.append(f"provider_source {PROVIDER_SOURCE_ID} 已更新")
            break
    else:
        sources.append(source)
        changed.append(f"provider_source {PROVIDER_SOURCE_ID} 已添加")

    providers = conf.setdefault("provider", [])
    entry = provider_entry()

    for i, existing in enumerate(providers):
        if existing.get("id") == PROVIDER_ID:
            if existing != entry:
                providers[i] = entry
                changed.append(f"provider {PROVIDER_ID} 已更新")
            break
    else:
        providers.append(entry)
        changed.append(f"provider {PROVIDER_ID} 已添加")

    settings = conf.setdefault("provider_settings", {})
    if settings.get("default_provider_id") != PROVIDER_ID:
        settings["default_provider_id"] = PROVIDER_ID
        changed.append(f"默认对话模型 -> {PROVIDER_ID}")
    return changed


def apply_persona_selection(conf: dict) -> list[str]:
    """Point ``default_personality`` at campuscue.

    The row itself goes into the database (``apply_persona_row``); this only
    selects it. PersonaManager reads the name from config and looks it up in the
    table, so the two halves have to agree.
    """
    from campuscue.persona import PERSONA_ID

    settings = conf.setdefault("provider_settings", {})
    if settings.get("default_personality") == PERSONA_ID:
        return []
    settings["default_personality"] = PERSONA_ID
    return [f"默认人格 -> {PERSONA_ID}"]


def platform_entry() -> dict:
    """The OneBot v11 (NapCat) adapter instance.

    Shape copied from the "OneBot v11" template in
    astrbot/core/config/default.py, because ``AiocqhttpAdapter.__init__`` indexes
    ``ws_reverse_host`` and ``ws_reverse_port`` directly -- a missing key is a
    KeyError during platform load, which PlatformManager swallows into a log line.

    Reverse WebSocket means astrbot listens and NapCat dials in, so nothing here
    needs to know NapCat's address. The token stays empty: both ends are on
    127.0.0.1 on the demo laptop, and a token neither side agrees on is the most
    common way this connection silently fails to establish.

    Bound to 127.0.0.1, not 0.0.0.0. NapCat runs on this same machine, so the
    loopback interface is the whole of what this socket needs to serve -- and the
    socket accepts any client that speaks the handshake, with no token by default.
    On conference or campus wifi, 0.0.0.0 offers that to every host on the
    network. Override with CAMPUSCUE_ONEBOT_HOST if NapCat ever runs elsewhere.
    """
    return {
        "id": PLATFORM_ID,
        "type": "aiocqhttp",
        "enable": True,
        "ws_reverse_host": os.environ.get("CAMPUSCUE_ONEBOT_HOST", "127.0.0.1"),
        "ws_reverse_port": int(
            os.environ.get("CAMPUSCUE_ONEBOT_PORT", DEFAULT_WS_PORT)
        ),
        "ws_reverse_token": os.environ.get("CAMPUSCUE_ONEBOT_TOKEN", ""),
    }


def apply_platform(conf: dict) -> list[str]:
    """Upsert the QQ adapter, then trim everything else.

    Provisioning the entry rather than documenting a click-path is the same
    argument as the provider: on-site, "add a platform, pick OneBot v11, set the
    port, save" is four chances to get it wrong while someone watches.
    """
    changed: list[str] = []
    platforms = conf.setdefault("platform", [])
    entry = platform_entry()

    for i, existing in enumerate(platforms):
        if existing.get("id") == PLATFORM_ID:
            if existing != entry:
                platforms[i] = entry
                changed.append(f"平台 {PLATFORM_ID}(aiocqhttp) 已更新")
            break
    else:
        platforms.append(entry)
        changed.append(
            f"平台 {PLATFORM_ID}(aiocqhttp) 已添加，反向 WS 端口 "
            f"{entry['ws_reverse_port']}"
        )
    return changed


def apply_whitelist_guard(conf: dict) -> list[str]:
    """Refuse to leave an enabled-but-empty session allowlist behind.

    ``WhitelistCheckStage`` returns early when the list is empty, so an enabled
    allowlist with nothing in it is silently permissive -- which reads on the
    config as if group access were restricted when it is not. Either state is
    defensible; a flag that means the opposite of what it says is not, and this
    is the file shown on a projector.
    """
    settings = conf.get("platform_settings")
    if not isinstance(settings, dict):
        return []
    entries = [str(i).strip() for i in settings.get("id_whitelist") or []]
    if settings.get("enable_id_white_list") and not any(entries):
        settings["enable_id_white_list"] = False
        return ["会话白名单为空，已关闭开关（空名单本就不生效）"]
    return []


def apply_dashboard(conf: dict) -> list[str]:
    """Keep the single-student board on this machine by default.

    CampusCue stores source messages and can mutate reminders through its HTTP
    API. The product is local-only, so inheriting AstrBot's historical
    ``0.0.0.0`` default would expose that data to the current Wi-Fi network.
    Authentication remains available for an explicitly configured remote
    deployment, but provisioning the local product always restores loopback.
    """
    dashboard = conf.setdefault("dashboard", {})
    if dashboard.get("host") == "127.0.0.1":
        return []
    dashboard["host"] = "127.0.0.1"
    return ["看板监听地址 -> 127.0.0.1（仅本机）"]


def dedupe_provider_sources(conf: dict) -> list[str]:
    """Drop duplicate ``provider_sources`` entries sharing an id.

    The WebUI appends a source row per save, so provisioning twice through it
    leaves two identical rows. Harmless until they diverge, at which point which
    one wins is load order.
    """
    sources = conf.get("provider_sources")
    if not isinstance(sources, list):
        return []
    seen: set[str] = set()
    kept: list[dict] = []
    dropped: list[str] = []
    for entry in sources:
        key = str(entry.get("id")) if isinstance(entry, dict) else repr(entry)
        if key in seen:
            dropped.append(key)
            continue
        seen.add(key)
        kept.append(entry)
    if not dropped:
        return []
    conf["provider_sources"] = kept
    return [f"provider_sources 去重：{', '.join(sorted(set(dropped)))}"]


def apply_platform_trim(conf: dict) -> list[str]:
    """Disable the adapters CampusCue does not use.

    Only entries that already exist are touched -- a clean config has an empty
    ``platform`` list, in which case there is nothing to trim and nothing to
    report.
    """
    changed: list[str] = []
    for entry in conf.get("platform", []):
        if entry.get("id") in UNUSED_ADAPTERS and entry.get("enable"):
            entry["enable"] = False
            changed.append(f"平台 {entry['id']} 已禁用")
    return changed


def apply_feature_trim(conf: dict) -> list[str]:
    """Turn off the subsystems a campus task agent has no use for.

    Each of these costs something real at startup or per message: a TTS/STT
    provider is a model download and an extra request, and the knowledge base
    wants an embedding provider CampusCue deliberately does not configure (see
    the plan on why FAISS is out of scope).
    """
    changed: list[str] = []
    for section, key in (
        ("provider_tts_settings", "enable"),
        ("provider_stt_settings", "enable"),
        ("provider_ltm_settings", "group_icl_enable"),
    ):
        block = conf.get(section)
        if isinstance(block, dict) and block.get(key):
            block[key] = False
            changed.append(f"{section}.{key} -> false")
    return changed


async def apply_persona_row() -> list[str]:
    """Create or update the ``personas`` row holding campuscue's prompt.

    Talks to the database directly rather than through PersonaManager: this runs
    as a standalone script with no live core, and ``insert_persona`` /
    ``update_persona`` are the same calls the manager would make.
    """
    from astrbot.core.config.default import DB_PATH
    from astrbot.core.db.sqlite import SQLiteDatabase
    from campuscue.persona import PERSONA_ID, SYSTEM_PROMPT

    db = SQLiteDatabase(DB_PATH)
    await db.initialize()
    try:
        existing = await db.get_persona_by_id(PERSONA_ID)
        if existing is None:
            await db.insert_persona(
                PERSONA_ID,
                SYSTEM_PROMPT,
                begin_dialogs=[],
                # None, not [] -- None means "all tools", an empty list would
                # mean "no tools" and silently disarm the five campus tools.
                tools=None,
                skills=None,
            )
            return [f"人格 {PERSONA_ID} 已写入数据库"]
        if existing.system_prompt != SYSTEM_PROMPT:
            await db.update_persona(PERSONA_ID, SYSTEM_PROMPT, [])
            return [f"人格 {PERSONA_ID} 提示词已更新"]
        return []
    finally:
        await db.engine.dispose()


def _auth_required() -> bool:
    """Whether the board is behind the dashboard session check.

    Same env var and same parsing as ``api/routes._maybe_require_auth``; read
    here so a check about exposure cannot disagree with the gate it describes.
    """
    return os.environ.get("CAMPUSCUE_REQUIRE_AUTH", "").strip() in ("1", "true", "yes")


async def collect_checks() -> list[tuple[str, bool, str]]:
    """Every readiness check as ``(group, ok, text)``, in report order.

    Split out from ``check()`` so the board's 接入与自检 page and the CLI ask the
    same questions of the same config. Two implementations of "is this ready" is
    how a page comes to say 全部就绪 about something the script calls broken.

    Returns early on a missing config file or database: everything after those
    would be reporting on a file that is not there, and a wall of MISS lines
    hides the one line that matters.
    """
    from campuscue.persona import PERSONA_ID

    out: list[tuple[str, bool, str]] = []
    group = "环境变量"

    def line(ok: bool, text: str) -> None:
        out.append((group, ok, text))

    line(bool(os.environ.get("DEEPSEEK_API_KEY")), "DEEPSEEK_API_KEY（对话模型）")
    line(bool(os.environ.get("ARK_API_KEY")), "ARK_API_KEY（抽取模型）")
    line(bool(os.environ.get("ARK_EXTRACT_MODEL")), "ARK_EXTRACT_MODEL")

    group = "配置文件"
    if not CONFIG_PATH.exists():
        line(False, f"{CONFIG_PATH.name} 不存在（先启动一次 main.py）")
        return out
    conf = read_config()
    providers = {p.get("id"): p for p in conf.get("provider", [])}
    sources = {s.get("id"): s for s in conf.get("provider_sources") or []}
    settings = conf.get("provider_settings", {})
    line(PROVIDER_ID in providers, f"provider 实例 {PROVIDER_ID}")
    line(PROVIDER_SOURCE_ID in sources, f"provider_source {PROVIDER_SOURCE_ID}")
    # The two halves are joined by this key at load time; a provider whose
    # source_id points at nothing loads with no api_base and no credentials.
    line(
        providers.get(PROVIDER_ID, {}).get("provider_source_id") == PROVIDER_SOURCE_ID,
        "provider 已关联到 provider_source（否则没有 api_base 和 key）",
    )
    line(
        settings.get("default_provider_id") == PROVIDER_ID,
        f"默认对话模型 = {PROVIDER_ID}（当前 {settings.get('default_provider_id') or '未设置'}）",
    )
    line(
        settings.get("default_personality") == PERSONA_ID,
        f"默认人格 = {PERSONA_ID}（当前 {settings.get('default_personality') or '未设置'}）",
    )
    enabled_unused = [
        e["id"]
        for e in conf.get("platform", [])
        if e.get("id") in UNUSED_ADAPTERS and e.get("enable")
    ]
    line(
        not enabled_unused, f"无关平台适配器已禁用（仍启用：{enabled_unused or '无'}）"
    )

    qq = next(
        (
            e
            for e in conf.get("platform", [])
            if e.get("id") == PLATFORM_ID and e.get("type") == "aiocqhttp"
        ),
        None,
    )
    line(qq is not None, f"QQ 适配器条目 {PLATFORM_ID}(aiocqhttp)")
    if qq is not None:
        line(
            bool(qq.get("enable")),
            f"QQ 适配器已启用，反向 WS 端口 {qq.get('ws_reverse_port')}",
        )
        # An OneBot socket that takes any client with no token, on every
        # interface, is an open door on whatever wifi the laptop joins next.
        onebot_host = qq.get("ws_reverse_host")
        line(
            onebot_host != "0.0.0.0" or bool(qq.get("ws_reverse_token")),
            f"OneBot 端口未对外暴露（绑定 {onebot_host}"
            f"{'，无 token' if not qq.get('ws_reverse_token') else ''}）",
        )

    # The board has no login by default, so where it listens decides who can read
    # the student's tasks. astrbot's own default is 0.0.0.0; flagged rather than
    # rewritten because the dashboard port is the base's config, not ours.
    dash = conf.get("dashboard", {}) or {}
    dash_host = dash.get("host", "0.0.0.0")
    board_open = dash_host == "0.0.0.0" and not _auth_required()
    line(
        not board_open,
        f"看板未对外开放（dashboard.host={dash_host}，"
        f"鉴权{'开' if _auth_required() else '关'}）"
        + (
            "；同网段任何人可读你的任务，设 CAMPUSCUE_REQUIRE_AUTH=1"
            if board_open
            else ""
        ),
    )

    wl = conf.get("platform_settings", {})
    wl_entries = [str(i).strip() for i in wl.get("id_whitelist") or []]
    line(
        not wl.get("enable_id_white_list") or any(wl_entries),
        "会话白名单开关与名单一致（开着但为空 = 实际不生效）",
    )
    source_ids = [s.get("id") for s in conf.get("provider_sources") or []]
    line(
        len(source_ids) == len(set(source_ids)),
        f"provider_sources 无重复（当前 {len(source_ids)} 条）",
    )

    group = "数据库"
    from astrbot.core.config.default import DB_PATH
    from astrbot.core.db.sqlite import SQLiteDatabase

    if not pathlib.Path(DB_PATH).exists():
        line(False, f"{pathlib.Path(DB_PATH).name} 不存在（先启动一次 main.py）")
        return out
    db = SQLiteDatabase(DB_PATH)
    await db.initialize()
    try:
        persona = await db.get_persona_by_id(PERSONA_ID)
        line(persona is not None, f"personas 表中的 {PERSONA_ID}")
        if persona is not None:
            from campuscue.persona import SYSTEM_PROMPT

            line(persona.system_prompt == SYSTEM_PROMPT, "人格提示词与 persona.py 一致")
            line(persona.tools is None, "人格未限制工具（None = 全部可用）")
    finally:
        await db.engine.dispose()

    return out


async def check() -> int:
    """Print the readiness report. Returns the number of problems, so this can
    gate a rehearsal script by exit code."""
    checks = await collect_checks()
    seen_group = ""
    problems = 0
    for group, ok, text in checks:
        if group != seen_group:
            print(group)
            seen_group = group
        print(f"  {'OK  ' if ok else 'MISS'}  {text}")
        if not ok:
            problems += 1
    return problems


async def provision() -> None:
    if not CONFIG_PATH.exists():
        print(f"找不到 {CONFIG_PATH}。先跑一次 main.py 生成默认配置。")
        raise SystemExit(1)
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY 未设置。写进 .env 再重跑。")
        raise SystemExit(1)

    conf = read_config()
    changes: list[str] = []
    changes += apply_provider(conf)
    changes += apply_persona_selection(conf)
    changes += apply_platform(conf)
    changes += apply_platform_trim(conf)
    changes += apply_feature_trim(conf)
    changes += apply_whitelist_guard(conf)
    changes += apply_dashboard(conf)
    changes += dedupe_provider_sources(conf)
    if changes:
        write_config(conf)
    changes += await apply_persona_row()

    if changes:
        print("已应用：")
        for c in changes:
            print(f"  - {c}")
    else:
        print("配置已是目标状态，无需改动。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="配置 CampusCue 的对话链路")
    parser.add_argument("--check", action="store_true", help="只检查，不修改任何文件")
    args = parser.parse_args(argv)

    load_env()
    if args.check:
        problems = asyncio.run(check())
        print(f"\n{problems} 项待处理。" if problems else "\n全部就绪。")
        return 1 if problems else 0
    asyncio.run(provision())
    return 0


if __name__ == "__main__":
    sys.exit(main())
