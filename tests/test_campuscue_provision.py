"""The conversation link: secrets reach the provider, and nothing leaks.

Three properties are pinned here, all of which failed at least once during
development and none of which show up as an exception:

* The provider's key stays a ``$NAME`` reference in config. If someone
  "fixes" it by pasting the literal key, ``data/cmd_config.json`` becomes a file
  that cannot be shown on a projector -- and the demo is given on a projector.
* ``.env`` is in the environment before providers load. astrbot has no dotenv
  step of its own, so CampusCue's star does it in ``__init__``. That only works
  because stars are instantiated before ``provider_manager.initialize()``, an
  ordering in upstream code that nothing else guards.
* Provisioning twice changes nothing the second time. ``--check`` exists so a
  rehearsal can be gated on it, which is worthless if running it moves things.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

from campuscue import provision
from campuscue.persona import PERSONA_ID


class TestProviderEntry:
    def test_the_key_is_an_env_reference_not_the_secret(self, monkeypatch):
        """The whole point of ``$DEEPSEEK_API_KEY``.

        ``ProviderManager._resolve_env_key_list`` expands it at load time, so the
        config file on disk never holds a credential.
        """
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-should-not-appear")

        source = provision.provider_source_entry()

        assert source["key"] == ["$DEEPSEEK_API_KEY"]
        assert "sk-should-not-appear" not in str(source)

    def test_it_is_an_openai_compatible_chat_provider(self):
        """DeepSeek needs no new provider class, but two fields have to be right:
        ``provider_type`` is what gates env-key expansion (manager.py:591), and
        ``type`` selects the adapter module. Both live on the source half, which
        is what ``get_merged_provider_config`` merges in before either is read."""
        source = provision.provider_source_entry()

        assert source["provider_type"] == "chat_completion"
        assert source["type"] == "openai_chat_completion"
        assert source["api_base"].startswith("https://api.deepseek.com")
        assert provision.provider_entry()["enable"] is True

    def test_the_two_halves_are_joined_by_provider_source_id(self):
        """The join key. A provider pointing at a source id that does not exist
        loads with no api_base and no credentials -- and does so quietly."""
        assert (
            provision.provider_entry()["provider_source_id"]
            == provision.provider_source_entry()["id"]
        )

    def test_the_provider_half_holds_only_fields_the_migration_leaves_alone(self):
        """Why this matters, and why it cost a duplicate row per boot:

        ``_migra_provider_to_source_structure`` rewrites any provider that has no
        ``provider_source_id``, moving everything outside ``provider_only_fields``
        into a newly appended ``<id>_source``. A provisioner writing the old flat
        entry and that migration therefore undo each other on every start, and
        ``provider_sources`` grows without bound.

        Asserted against the upstream field list rather than a copy of it, so a
        change upstream fails here.
        """
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "astrbot"
            / "core"
            / "utils"
            / "migra_helper.py"
        ).read_text(encoding="utf-8")
        block = source[source.index("provider_only_fields = {") :]
        allowed = {
            line.strip().strip('",')
            for line in block[: block.index("}")].splitlines()[1:]
        }

        assert allowed, "could not parse provider_only_fields from upstream"
        assert set(provision.provider_entry()) <= allowed, (
            "extra fields here make the migration split this provider again and "
            "append another provider_sources row on every boot"
        )

    def test_provisioning_writes_both_halves(self):
        conf: dict = {}

        provision.apply_provider(conf)

        assert [s["id"] for s in conf["provider_sources"]] == [
            provision.PROVIDER_SOURCE_ID
        ]
        assert [p["id"] for p in conf["provider"]] == [provision.PROVIDER_ID]

    def test_an_existing_source_is_updated_in_place_not_appended(self):
        """The exact failure this replaced: one duplicate row per provisioning."""
        conf: dict = {}
        provision.apply_provider(conf)
        provision.apply_provider(conf)
        provision.apply_provider(conf)

        assert len(conf["provider_sources"]) == 1


class TestApplyConfig:
    def test_provisioning_a_bare_config_adds_the_provider_and_selects_it(self):
        conf: dict = {}

        changes = provision.apply_provider(conf)

        assert [p["id"] for p in conf["provider"]] == [provision.PROVIDER_ID]
        assert conf["provider_settings"]["default_provider_id"] == (
            provision.PROVIDER_ID
        )
        assert changes

    def test_running_it_again_reports_no_changes(self):
        """Idempotence is what makes ``--check`` trustworthy before a demo."""
        conf: dict = {}
        provision.apply_provider(conf)
        provision.apply_persona_selection(conf)

        assert provision.apply_provider(conf) == []
        assert provision.apply_persona_selection(conf) == []

    def test_an_existing_instance_is_updated_in_place_not_duplicated(self):
        """Two entries with the same id would make which one loads a coin flip."""
        conf = {"provider": [{"id": provision.PROVIDER_ID, "enable": False}]}

        provision.apply_provider(conf)

        assert len(conf["provider"]) == 1
        assert conf["provider"][0]["enable"] is True

    def test_an_unrelated_provider_is_left_alone(self):
        conf = {"provider": [{"id": "someone-elses-model", "enable": True}]}

        provision.apply_provider(conf)

        ids = [p["id"] for p in conf["provider"]]
        assert "someone-elses-model" in ids
        assert conf["provider"][0]["enable"] is True

    def test_the_persona_selection_matches_the_row_provisioning_writes(self):
        """PersonaManager looks the name up in the ``personas`` table, so config
        and database have to agree or the prompt silently never applies."""
        conf: dict = {}

        provision.apply_persona_selection(conf)

        assert conf["provider_settings"]["default_personality"] == PERSONA_ID

    def test_platform_trim_disables_only_unused_adapters_that_are_on(self):
        conf = {
            "platform": [
                {"id": "telegram", "enable": True},
                {"id": "discord", "enable": False},
                {"id": "aiocqhttp", "enable": True},
            ]
        }

        changes = provision.apply_platform_trim(conf)

        by_id = {e["id"]: e for e in conf["platform"]}
        assert by_id["telegram"]["enable"] is False
        assert by_id["aiocqhttp"]["enable"] is True, "the real QQ path must survive"
        assert len(changes) == 1, "an already-disabled adapter is not a change"

    def test_aiocqhttp_and_webchat_are_never_in_the_trim_list(self):
        """The two adapters the product actually runs on."""
        assert "aiocqhttp" not in provision.UNUSED_ADAPTERS
        assert "webchat" not in provision.UNUSED_ADAPTERS

    def test_feature_trim_turns_off_subsystems_campuscue_does_not_configure(self):
        conf = {
            "provider_tts_settings": {"enable": True},
            "provider_stt_settings": {"enable": True},
            "provider_ltm_settings": {"group_icl_enable": True},
        }

        provision.apply_feature_trim(conf)

        assert conf["provider_tts_settings"]["enable"] is False
        assert conf["provider_stt_settings"]["enable"] is False
        assert conf["provider_ltm_settings"]["group_icl_enable"] is False

    def test_feature_trim_tolerates_a_config_without_those_sections(self):
        """A trimmed config may not have them at all; a KeyError here would abort
        provisioning after the provider was already written."""
        conf: dict = {}

        assert provision.apply_feature_trim(conf) == []

    def test_dashboard_is_loopback_only(self):
        conf = {"dashboard": {"host": "0.0.0.0", "port": 6185}}

        changes = provision.apply_dashboard(conf)

        assert conf["dashboard"] == {"host": "127.0.0.1", "port": 6185}
        assert changes

    def test_dashboard_loopback_migration_is_idempotent(self):
        conf: dict = {}

        provision.apply_dashboard(conf)

        assert provision.apply_dashboard(conf) == []
        assert conf["dashboard"]["host"] == "127.0.0.1"


class TestQQPlatform:
    """The inbound path. Without an entry here astrbot listens on no OneBot port
    at all, and NapCat's reverse WebSocket has nothing to dial."""

    def test_the_entry_has_every_field_the_adapter_indexes(self):
        """``AiocqhttpAdapter.__init__`` does ``platform_config["ws_reverse_host"]``
        and ``["ws_reverse_port"]`` unguarded. A missing key becomes a swallowed
        log line in PlatformManager, i.e. a bot that boots and never connects."""
        entry = provision.platform_entry()

        assert entry["type"] == "aiocqhttp"
        assert entry["enable"] is True
        assert isinstance(entry["ws_reverse_port"], int)
        assert "ws_reverse_token" in entry

    def test_the_onebot_socket_is_loopback_only(self, monkeypatch):
        """NapCat is local, and this socket takes any client with no token.

        On 0.0.0.0 that is an open OneBot endpoint for every host on whatever
        conference or campus wifi the laptop is on.
        """
        monkeypatch.delenv("CAMPUSCUE_ONEBOT_HOST", raising=False)
        assert provision.platform_entry()["ws_reverse_host"] == "127.0.0.1"

    def test_a_remote_napcat_can_still_be_configured(self, monkeypatch):
        monkeypatch.setenv("CAMPUSCUE_ONEBOT_HOST", "0.0.0.0")
        assert provision.platform_entry()["ws_reverse_host"] == "0.0.0.0"

    def test_the_port_matches_the_builtin_onebot_template(self):
        """So configuring it through the WebUI instead lands on the same port and
        NapCat does not have to be reconfigured."""
        assert provision.platform_entry()["ws_reverse_port"] == 6199

    def test_the_port_can_be_overridden_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CAMPUSCUE_ONEBOT_PORT", "6299")

        assert provision.platform_entry()["ws_reverse_port"] == 6299

    def test_provisioning_a_bare_config_adds_the_qq_adapter(self):
        conf: dict = {}

        changes = provision.apply_platform(conf)

        assert [p["id"] for p in conf["platform"]] == [provision.PLATFORM_ID]
        assert conf["platform"][0]["type"] == "aiocqhttp"
        assert changes

    def test_running_it_again_reports_no_changes(self):
        conf: dict = {}
        provision.apply_platform(conf)

        assert provision.apply_platform(conf) == []

    def test_an_existing_disabled_entry_is_re_enabled_not_duplicated(self):
        """Two aiocqhttp instances on one port means the second fails to bind."""
        conf = {
            "platform": [
                {"id": provision.PLATFORM_ID, "type": "aiocqhttp", "enable": False}
            ]
        }

        provision.apply_platform(conf)

        assert len(conf["platform"]) == 1
        assert conf["platform"][0]["enable"] is True

    def test_a_platform_someone_else_added_is_left_alone(self):
        conf = {"platform": [{"id": "my-own-bot", "type": "telegram", "enable": True}]}

        provision.apply_platform(conf)

        ids = [p["id"] for p in conf["platform"]]
        assert ids == ["my-own-bot", provision.PLATFORM_ID]

    def test_the_platform_id_is_the_first_segment_of_every_qq_umo(self):
        """Asserted against upstream source because it is easy to get backwards.

        ``AstrMessageEvent.__init__`` builds the session with
        ``platform_name=platform_meta.id`` -- the adapter *instance id*, not the
        adapter type. So PLATFORM_ID lands in every umo the QQ path produces, and
        changing it orphans every stored task, source row and reminder. If a
        refactor switches that to ``platform_meta.name`` this test says so.
        """
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "astrbot"
            / "core"
            / "platform"
            / "astr_message_event.py"
        ).read_text(encoding="utf-8")

        assert "platform_name=platform_meta.id" in source, (
            "umo's first segment is the platform instance id; campuscue stores "
            "tasks keyed on it and provision.PLATFORM_ID is chosen accordingly"
        )

    def test_the_trim_does_not_disable_the_entry_we_just_added(self):
        """Both run in ``provision()``, in this order. If PLATFORM_ID ever ended up
        in UNUSED_ADAPTERS the two would fight and the QQ path would die."""
        conf: dict = {}

        provision.apply_platform(conf)
        provision.apply_platform_trim(conf)

        assert conf["platform"][0]["enable"] is True


class TestWhitelistGuard:
    def test_an_enabled_but_empty_allowlist_is_switched_off(self):
        """``WhitelistCheckStage`` returns early on an empty list, so this flag
        claims a restriction that does not exist."""
        conf = {"platform_settings": {"enable_id_white_list": True, "id_whitelist": []}}

        changes = provision.apply_whitelist_guard(conf)

        assert conf["platform_settings"]["enable_id_white_list"] is False
        assert changes

    def test_blank_strings_do_not_count_as_entries(self):
        """The stage strips and drops empties before checking, so ``[" "]`` is an
        empty allowlist to it and must be one here too."""
        conf = {
            "platform_settings": {"enable_id_white_list": True, "id_whitelist": ["  "]}
        }

        provision.apply_whitelist_guard(conf)

        assert conf["platform_settings"]["enable_id_white_list"] is False

    def test_a_real_allowlist_is_left_switched_on(self):
        conf = {
            "platform_settings": {
                "enable_id_white_list": True,
                "id_whitelist": ["aiocqhttp:GroupMessage:123"],
            }
        }

        assert provision.apply_whitelist_guard(conf) == []
        assert conf["platform_settings"]["enable_id_white_list"] is True

    def test_an_already_disabled_switch_is_not_a_change(self):
        conf = {
            "platform_settings": {"enable_id_white_list": False, "id_whitelist": []}
        }

        assert provision.apply_whitelist_guard(conf) == []

    def test_a_config_without_platform_settings_is_tolerated(self):
        assert provision.apply_whitelist_guard({}) == []


class TestProviderSourceDedupe:
    def test_duplicate_ids_are_collapsed_keeping_the_first(self):
        conf = {
            "provider_sources": [
                {"id": "a", "api_base": "first"},
                {"id": "a", "api_base": "second"},
                {"id": "b"},
            ]
        }

        changes = provision.dedupe_provider_sources(conf)

        assert [s["id"] for s in conf["provider_sources"]] == ["a", "b"]
        assert conf["provider_sources"][0]["api_base"] == "first"
        assert changes

    def test_a_clean_list_reports_nothing(self):
        conf = {"provider_sources": [{"id": "a"}, {"id": "b"}]}

        assert provision.dedupe_provider_sources(conf) == []
        assert len(conf["provider_sources"]) == 2

    def test_a_missing_section_is_tolerated(self):
        assert provision.dedupe_provider_sources({}) == []


class TestEnvLoadingOnBoot:
    def test_constructing_the_star_loads_dotenv(self, monkeypatch):
        """Without this the DeepSeek key is absent when providers initialize and
        the agent path dies with "Missing credentials" -- while extraction and
        reminders keep working, so the failure is quiet."""
        from astrbot.builtin_stars.campuscue import main as star_main
        from campuscue.extractor import llm

        calls: list[object] = []
        monkeypatch.setattr(llm, "load_env_file", lambda *a: calls.append(a))

        star_main.CampusCue(context=SimpleNamespace())

        assert calls, "star.__init__ must load .env"

    def test_stars_are_instantiated_before_providers_initialize(self):
        """The ordering the fix depends on, asserted against upstream source.

        ``core_lifecycle.initialize`` calls ``plugin_manager.reload()`` (which
        constructs every Star) and only afterwards
        ``provider_manager.initialize()``. If a refactor swaps them, the star's
        dotenv load happens too late and the provider loses its key again. This
        test fails at that moment instead of at the next demo.
        """
        source = (
            pathlib.Path(__file__).resolve().parents[1]
            / "astrbot"
            / "core"
            / "core_lifecycle.py"
        ).read_text(encoding="utf-8")

        stars_at = source.index("plugin_manager.reload()")
        providers_at = source.index("provider_manager.initialize()")

        assert stars_at < providers_at, (
            "CampusCue loads .env in its star __init__; providers must be "
            "initialized after stars are constructed"
        )

    def test_dotenv_never_overwrites_an_already_set_variable(
        self, tmp_path, monkeypatch
    ):
        """Deployments set real environment variables. A .env left over from
        local testing must not shadow them."""
        from campuscue.extractor.llm import load_env_file

        (tmp_path / ".env").write_text(
            "DEEPSEEK_API_KEY=from-dotenv\nARK_API_KEY=from-dotenv\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("DEEPSEEK_API_KEY", "from-environment")
        monkeypatch.delenv("ARK_API_KEY", raising=False)

        load_env_file(tmp_path)

        import os

        assert os.environ["DEEPSEEK_API_KEY"] == "from-environment"
        assert os.environ["ARK_API_KEY"] == "from-dotenv"

    def test_a_missing_dotenv_is_not_an_error(self, tmp_path):
        """A clone with no .env must still boot: reminders and the board work
        without any model at all."""
        from campuscue.extractor.llm import load_env_file

        load_env_file(tmp_path)  # no .env in tmp_path
