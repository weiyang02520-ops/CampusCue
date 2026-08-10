"""M2a.1 regression tests: provider.test path, timeout contract, enum enforcement,
schema zero-mutation, clock injection, secret_reference early validation,
get_by_id, strict success parsing, status-first classification."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from campuscue.providers.errors import ProviderError, ProviderErrorCode
from campuscue.providers.manager import ProviderManager
from campuscue.providers.models import LLMMessage, LLMRequest
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.providers.validation import is_valid_secret_reference, validate_secret_reference


@pytest.fixture
async def db_session_factory(tmp_path):
    """Real temp SQLite + ProviderConfigRepository (integration-grade fixture)."""
    from campuscue.repositories.repositories import ProviderConfigRepository
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "p.db", env="test"))
    await database.initialize()
    repo = ProviderConfigRepository(database.session)
    repo._database = database  # expose for tests that need the raw db file
    yield repo
    await database.dispose()


@pytest.fixture
async def db_session_factory_raw(tmp_path):
    """Real temp SQLite Database object (for repository tests needing session factory)."""
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "raw.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


def _ok_response(content="PONG"):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"total_tokens": 3},
        },
    )


def _provider_with(handler, **kw):
    return OpenAICompatibleProvider(
        base_url="https://api.example.com/v1/",
        model="gpt-4o",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        **kw,
    )


# ------------------------------------------------------------------ A: test() real path

class TestProviderTestRealPath:
    @pytest.mark.asyncio
    async def test_provider_test_via_mock_transport(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return _ok_response(content="PONG")

        p = _provider_with(handler)
        result = await p.test()
        assert result["ok"] is True
        assert result["reply"] == "PONG"
        assert seen["url"].endswith("/chat/completions")

    @pytest.mark.asyncio
    async def test_provider_test_failure_classified(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, text="unauthorized plain text")

        p = _provider_with(handler)
        with pytest.raises(ProviderError) as ei:
            await p.test()
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_provider_manager_test_default_real_chain(self, db_session_factory, monkeypatch):
        """ProviderManager.get_default -> OpenAICompatibleProvider.test
        -> chat -> transport -> parse -> safe result (no mocks of test() itself)."""
        monkeypatch.setenv("TEST_FAKE_PROVIDER_KEY", "fake-value")

        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return _ok_response(content="PONG")

        cfg = await db_session_factory.create(
            name="default", base_url="https://api.example.com/v1", model="gpt-4o",
            secret_reference="TEST_FAKE_PROVIDER_KEY",
        )
        # real manager chain: get_default -> provider.test -> chat -> transport
        mgr = ProviderManager(db_session_factory)
        provider = await mgr.get_default()
        provider._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        result = await provider.test()
        assert result["ok"] is True
        assert result["reply"] == "PONG"
        assert seen["auth"] == "Bearer fake-value"

    @pytest.mark.asyncio
    async def test_provider_manager_test_default_uses_real_default(self, db_session_factory, monkeypatch):
        """test_default routes through get_default (exactly-one rule) to the real path."""
        monkeypatch.setenv("TEST_FAKE_PROVIDER_KEY", "fake-value")

        def handler(request: httpx.Request) -> httpx.Response:
            return _ok_response(content="PONG")

        await db_session_factory.create(
            name="only", base_url="https://api.example.com/v1", model="gpt-4o",
            secret_reference="TEST_FAKE_PROVIDER_KEY",
        )
        # patch the manager's instantiated provider client via a subclass hook:
        original_instantiate = ProviderManager._instantiate

        def patched_instantiate(self, cfg):
            p = original_instantiate(self, cfg)
            p._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
            return p

        ProviderManager._instantiate = patched_instantiate
        try:
            mgr = ProviderManager(db_session_factory)
            result = await mgr.test_default()
            assert result["ok"] is True
            assert result["reply"] == "PONG"
        finally:
            ProviderManager._instantiate = original_instantiate


# ------------------------------------------------------------------ B: timeout contract

class TestRequestTimeoutContract:
    @pytest.mark.asyncio
    async def test_request_timeout_overrides_provider_default(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return _ok_response()

        p = _provider_with(handler, timeout_s=60.0)
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")], model="gpt-4o", timeout_s=5.0
        ))
        # httpx expands timeout into per-phase dict; all phases must carry the override
        assert seen["timeout"]["read"] == 5.0  # request override wins

    @pytest.mark.asyncio
    async def test_provider_default_used_when_request_no_override(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["timeout"] = request.extensions.get("timeout")
            return _ok_response()

        p = _provider_with(handler, timeout_s=42.0)
        await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert seen["timeout"]["read"] == 42.0

    @pytest.mark.asyncio
    async def test_zero_request_timeout_rejected(self):
        p = _provider_with(lambda r: _ok_response())
        with pytest.raises(ProviderError, match="timeout"):
            await p.chat(LLMRequest(
                messages=[LLMMessage(role="user", content="hi")], model="gpt-4o", timeout_s=0
            ))

    def test_provider_numeric_validation(self):
        from campuscue.providers.validation import validate_provider_config_numeric

        with pytest.raises(ValueError, match="timeout_s"):
            validate_provider_config_numeric(timeout_s=0)
        with pytest.raises(ValueError, match="max_tokens"):
            validate_provider_config_numeric(max_tokens=-1)
        with pytest.raises(ValueError, match="max_context_tokens"):
            validate_provider_config_numeric(max_context_tokens=0)
        with pytest.raises(ValueError, match="temperature"):
            validate_provider_config_numeric(temperature=-0.5)
        validate_provider_config_numeric(timeout_s=1.0, max_tokens=10, temperature=0.0)  # OK


# ------------------------------------------------------------------ C: closed enums

class TestEnumEnforcement:
    @pytest.mark.asyncio
    async def test_invalid_task_status_rejected(self, db_session_factory_raw):
        from campuscue.repositories.repositories import TaskRepository

        repo = TaskRepository(db_session_factory_raw.session)
        with pytest.raises(ValueError, match="status"):
            await repo.create(title="x", status="banana")

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self, db_session_factory_raw):
        from campuscue.repositories.repositories import TaskRepository

        repo = TaskRepository(db_session_factory_raw.session)
        with pytest.raises(ValueError, match="category"):
            await repo.create(title="x", category="whatever")

    @pytest.mark.asyncio
    async def test_invalid_priority_rejected(self, db_session_factory_raw):
        from campuscue.repositories.repositories import TaskRepository

        repo = TaskRepository(db_session_factory_raw.session)
        with pytest.raises(ValueError, match="priority"):
            await repo.create(title="x", priority="urgent_plus_plus")

    @pytest.mark.asyncio
    async def test_invalid_extraction_status_rejected(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ExtractionRepository

        repo = ExtractionRepository(db_session_factory_raw.session)
        with pytest.raises(ValueError, match="status"):
            await repo.create(source_id=None, source_message_id="m", trace_id="t", status="made_up")

    @pytest.mark.asyncio
    async def test_all_canonical_values_pass(self, db_session_factory_raw):
        from campuscue.repositories.repositories import TaskRepository
        from campuscue.storage.enums import TaskStatus

        repo = TaskRepository(db_session_factory_raw.session)
        for status in TaskStatus:
            t = await repo.create(title=status.value, status=status.value)
            assert t.status == status.value

    @pytest.mark.asyncio
    async def test_db_level_check_constraint_blocks_direct_insert(self, db_session_factory):
        """DB defense-in-depth: raw SQL insert with invalid enum must fail at DB level."""
        import sqlite3 as _sqlite3

        # locate the underlying db file through the fixture's Database object
        database = db_session_factory._database
        path = str(database._config.path)
        conn = _sqlite3.connect(path)
        with pytest.raises(_sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO tasks (title, category, status, priority, created_at, updated_at) "
                "VALUES ('x', 'homework', 'banana', 'normal', '2026-08-10 00:00:00', '2026-08-10 00:00:00')"
            )
        conn.close()


# ------------------------------------------------------------------ D: schema zero-mutation

class TestSchemaZeroMutation:
    def _setup_future_version(self, tmp_path, version=999):
        path = tmp_path / "future.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE schema_meta (id INTEGER PRIMARY KEY AUTOINCREMENT, schema_version INTEGER NOT NULL UNIQUE)")
        conn.execute("INSERT INTO schema_meta (schema_version) VALUES (?)", (version,))
        conn.commit()
        conn.close()
        return path

    @pytest.mark.asyncio
    async def test_future_version_refused_no_mutation(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        path = self._setup_future_version(tmp_path)
        db = Database(DatabaseConfig(path=path, env="test"))
        with pytest.raises(SchemaRefusedError, match="unsupported schema version"):
            await db.initialize()
        # ZERO mutation: no current tables created, version row unchanged
        conn = sqlite3.connect(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "tasks" not in tables
        assert "sources" not in tables
        versions = [r[0] for r in conn.execute("SELECT schema_version FROM schema_meta")]
        assert versions == [999]
        conn.close()

    @pytest.mark.asyncio
    async def test_future_version_without_current_tables_not_created(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        path = self._setup_future_version(tmp_path)
        db = Database(DatabaseConfig(path=path, env="test"))
        with pytest.raises(SchemaRefusedError):
            await db.initialize()
        conn = sqlite3.connect(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        # sqlite_sequence may appear from the AUTOINCREMENT table; no application tables added
        assert tables <= {"schema_meta", "sqlite_sequence"}
        conn.close()

    @pytest.mark.asyncio
    async def test_unknown_db_with_tables_no_schema_meta_refused(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        path = tmp_path / "unknown.db"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE user_data (id INTEGER)")
        conn.commit()
        conn.close()
        db = Database(DatabaseConfig(path=path, env="test"))
        with pytest.raises(SchemaRefusedError, match="no schema_meta"):
            await db.initialize()
        conn = sqlite3.connect(path)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables == {"user_data"}  # untouched
        conn.close()

    @pytest.mark.asyncio
    async def test_unsupported_older_version_refused(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig, SchemaRefusedError

        path = self._setup_future_version(tmp_path, version=0)  # older
        db = Database(DatabaseConfig(path=path, env="test"))
        with pytest.raises(SchemaRefusedError, match="unsupported schema version"):
            await db.initialize()

    @pytest.mark.asyncio
    async def test_fresh_db_bootstrap_and_reopen(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.storage.models import SCHEMA_VERSION, SchemaMeta
        from sqlalchemy import select

        path = tmp_path / "fresh.db"
        db1 = Database(DatabaseConfig(path=path, env="test"))
        await db1.initialize()
        async with db1.session() as s:
            versions = list((await s.scalars(select(SchemaMeta.schema_version))).all())
        assert versions == [SCHEMA_VERSION]
        await db1.dispose()
        db2 = Database(DatabaseConfig(path=path, env="test"))
        await db2.initialize()  # reopen OK
        await db2.dispose()


# ------------------------------------------------------------------ E: clock injection

class TestClockInjection:
    @pytest.mark.asyncio
    async def test_fixed_clock_controls_created_at(self, tmp_path):
        from campuscue.storage.clock import FixedClock
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.repositories.repositories import SourceRepository

        fixed = datetime(2026, 8, 10, 12, 0, 0, tzinfo=timezone.utc)
        db = Database(DatabaseConfig(path=tmp_path / "clock.db", env="test"))
        await db.initialize()
        repo = SourceRepository(db.session, clock=FixedClock(fixed))
        src = await repo.create(platform="onebot", conversation_id="c1")
        assert src.created_at == fixed
        assert src.updated_at == fixed
        await db.dispose()

    @pytest.mark.asyncio
    async def test_fixed_clock_advance_deterministic(self, tmp_path):
        from campuscue.storage.clock import FixedClock
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.repositories.repositories import SourceRepository

        clock = FixedClock(datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc))
        db = Database(DatabaseConfig(path=tmp_path / "clock2.db", env="test"))
        await db.initialize()
        repo = SourceRepository(db.session, clock=clock)
        src = await repo.create(platform="onebot", conversation_id="c1")
        clock.advance(3600)
        updated = await repo.update(src.id, name="new")
        assert updated.updated_at == datetime(2026, 8, 10, 1, 0, 0, tzinfo=timezone.utc)
        assert updated.created_at == datetime(2026, 8, 10, 0, 0, 0, tzinfo=timezone.utc)
        await db.dispose()

    @pytest.mark.asyncio
    async def test_naive_clock_rejected(self, tmp_path):
        from campuscue.storage.database import Database, DatabaseConfig
        from campuscue.repositories.repositories import SourceRepository

        class NaiveClock:
            def utcnow(self):
                return datetime(2026, 8, 10, 0, 0, 0)  # naive!

        db = Database(DatabaseConfig(path=tmp_path / "clock3.db", env="test"))
        await db.initialize()
        repo = SourceRepository(db.session, clock=NaiveClock())
        with pytest.raises(ValueError, match="timezone-aware"):
            await repo.create(platform="onebot", conversation_id="c1")
        await db.dispose()


# ------------------------------------------------------------------ F: secret_reference early validation

class TestSecretReferenceEarlyValidation:
    def test_valid_references(self):
        validate_secret_reference(None)
        validate_secret_reference("CAMPUSCUE_LLM_API_KEY")
        validate_secret_reference("A_B")
        assert is_valid_secret_reference("CAMPUSCUE_LLM_API_KEY") is True

    @pytest.mark.parametrize("bad", ["", "BAD REF", "../secret", "$KEY", "key-name", "path/to/key", "a", "1ABC"])
    def test_invalid_references(self, bad):
        with pytest.raises(ValueError, match="secret_reference"):
            validate_secret_reference(bad)
        assert is_valid_secret_reference(bad) is False

    @pytest.mark.asyncio
    async def test_repository_rejects_invalid_before_persistence(self, db_session_factory):
        with pytest.raises(ValueError, match="secret_reference"):
            await db_session_factory.create(
                name="bad", base_url="https://x/v1", model="m", secret_reference="BAD REF"
            )

    @pytest.mark.asyncio
    async def test_provider_rejects_invalid_before_http(self, monkeypatch):
        # M2a.2: canonical validation at construction fails fast (no HTTP possible)
        with pytest.raises(ValueError, match="secret_reference"):
            OpenAICompatibleProvider(
                base_url="https://x/v1", model="m", secret_reference="../secret",
                client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _ok_response())),
            )


# ------------------------------------------------------------------ 15: get_by_id

class TestProviderManagerGetById:
    @pytest.mark.asyncio
    async def test_get_by_id_instantiates(self, db_session_factory):
        from campuscue.repositories.repositories import NotFoundError

        cfg = await db_session_factory.create(name="x", base_url="https://x/v1", model="m9")
        mgr = ProviderManager(db_session_factory)
        provider = await mgr.get_by_id(cfg.id)
        assert provider._model == "m9"

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, db_session_factory):
        from campuscue.repositories.repositories import NotFoundError

        mgr = ProviderManager(db_session_factory)
        with pytest.raises(NotFoundError):
            await mgr.get_by_id(99999)


# ------------------------------------------------------------------ 16: strict success parsing

class TestStrictSuccessParsing:
    @pytest.mark.asyncio
    async def test_missing_choices(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"id": "x"}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_empty_choices(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"choices": []}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_missing_message(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"choices": [{"index": 0}]}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_missing_content(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"role": "assistant"}}]}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_null_content(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None}}]}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_wrong_content_type(self):
        p = _provider_with(lambda r: httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": ["not", "str"]}}]}))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT


# ------------------------------------------------------------------ 17: status-first classification

class TestStatusFirstClassification:
    @pytest.mark.asyncio
    async def test_401_plain_text(self):
        p = _provider_with(lambda r: httpx.Response(401, text="unauthorized"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_403_html(self):
        p = _provider_with(lambda r: httpx.Response(403, text="<html>forbidden</html>"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_429_plain_text(self):
        p = _provider_with(lambda r: httpx.Response(429, text="slow down"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_500_html(self):
        p = _provider_with(lambda r: httpx.Response(500, text="<html>internal</html>"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.SERVER_ERROR

    @pytest.mark.asyncio
    async def test_400_plain_text(self):
        p = _provider_with(lambda r: httpx.Response(400, text="bad param plain"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_200_plain_text_malformed(self):
        p = _provider_with(lambda r: httpx.Response(200, text="not json"))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="m"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT
