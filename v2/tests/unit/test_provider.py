"""M2a provider unit/contract tests. httpx.MockTransport — never the Internet."""

from __future__ import annotations

import json
import os

import httpx
import pytest

from campuscue.providers.errors import (
    AmbiguousDefaultProviderError,
    NoProviderConfiguredError,
    ProviderError,
    ProviderErrorCode,
)
from campuscue.providers.manager import ProviderManager
from campuscue.providers.models import LLMMessage, LLMRequest
from campuscue.providers.openai_compatible import OpenAICompatibleProvider


def _ok_response(model="gpt-4o"):
    return httpx.Response(
        200,
        json={
            "id": "x", "model": model, "choices": [{"message": {"role": "assistant", "content": "PONG"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
    )


def _make_provider(*, base_url="https://api.example.com/v1/", secret_ref=None, **kw):
    return OpenAICompatibleProvider(
        base_url=base_url, model="gpt-4o", secret_reference=secret_ref, **kw
    )


class TestURLAndPayload:
    def test_endpoint_normalized_no_duplicate_slash(self):
        p = _make_provider(base_url="https://api.example.com/v1")
        assert p.endpoint == "https://api.example.com/v1/chat/completions"
        p2 = _make_provider(base_url="https://api.example.com/v1/")
        assert p2.endpoint == "https://api.example.com/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_structured_schema_reaches_response_format(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return _ok_response()

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        schema = {"type": "object", "properties": {"has_task": {"type": "boolean"}}, "required": ["has_task"]}
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")],
            model="gpt-4o",
            response_schema=schema,
        ))
        assert seen["url"] == "https://api.example.com/v1/chat/completions"
        rf = seen["body"]["response_format"]
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["schema"] == schema
        assert rf["json_schema"]["strict"] is True

    @pytest.mark.asyncio
    async def test_no_response_format_when_no_schema(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = json.loads(request.content)
            return _ok_response()

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert "response_format" not in seen["body"]


class TestAuth:
    @pytest.mark.asyncio
    async def test_bearer_auth_when_secret_resolved(self, monkeypatch):
        seen = {}
        monkeypatch.setenv("TEST_FAKE_PROVIDER_KEY", "fake-secret-value")

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return _ok_response()

        p = _make_provider(secret_ref="TEST_FAKE_PROVIDER_KEY",
                           client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert seen["auth"] == "Bearer fake-secret-value"

    @pytest.mark.asyncio
    async def test_no_auth_when_secret_absent(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["auth"] = request.headers.get("Authorization")
            return _ok_response()

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert seen["auth"] is None

    @pytest.mark.asyncio
    async def test_invalid_secret_reference_format_rejected(self, monkeypatch):
        monkeypatch.delenv("BAD REF!", raising=False)
        p = _make_provider(secret_ref="BAD REF WITH SPACES")
        with pytest.raises(ProviderError, match="secret_reference"):
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))

    @pytest.mark.asyncio
    async def test_secret_not_in_error(self, monkeypatch, caplog):
        monkeypatch.setenv("TEST_FAKE_PROVIDER_KEY", "super-secret-value-42")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"error": {"message": "bad key"}})

        p = _make_provider(secret_ref="TEST_FAKE_PROVIDER_KEY",
                           client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR
        assert "super-secret-value-42" not in str(ei.value)
        assert "super-secret-value-42" not in caplog.text


class TestChat:
    @pytest.mark.asyncio
    async def test_successful_chat(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: _ok_response())))
        resp = await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert resp.role == "assistant"
        assert resp.content == "PONG"
        assert resp.usage["total_tokens"] == 7
        assert resp.raw["id"] == "x"

    @pytest.mark.asyncio
    async def test_missing_choices_malformed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "x"})

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT

    @pytest.mark.asyncio
    async def test_malformed_http_json(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="this is not json")

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.MALFORMED_OUTPUT


class TestErrorClassification:
    @pytest.mark.asyncio
    async def test_timeout(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("boom", request=request)

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.TIMEOUT

    @pytest.mark.asyncio
    async def test_network_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.NETWORK

    @pytest.mark.asyncio
    async def test_401_auth(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={"error": {"message": "unauthorized"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_403_auth(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(403, json={"error": {"message": "forbidden"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.AUTH_ERROR

    @pytest.mark.asyncio
    async def test_429_rate_limit(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(429, json={"error": {"message": "rate limited"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.RATE_LIMIT

    @pytest.mark.asyncio
    async def test_400_invalid_model(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": {"message": "model 'gpt-4o' does not exist"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.INVALID_MODEL

    @pytest.mark.asyncio
    async def test_400_context_overflow(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": {"message": "maximum context length exceeded"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.CONTEXT_OVERFLOW

    @pytest.mark.asyncio
    async def test_400_generic_invalid_request(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": {"message": "bad param"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.INVALID_REQUEST

    @pytest.mark.asyncio
    async def test_500_server_error(self):
        p = _make_provider(client=httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(500, json={"error": {"message": "internal"}}))))
        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(messages=[LLMMessage(role="user", content="hi")], model="gpt-4o"))
        assert ei.value.code == ProviderErrorCode.SERVER_ERROR


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


class TestProviderManager:
    @pytest.mark.asyncio
    async def test_zero_enabled_no_provider(self, db_session_factory):
        mgr = ProviderManager(db_session_factory)
        with pytest.raises(NoProviderConfiguredError):
            await mgr.get_default()

    @pytest.mark.asyncio
    async def test_one_enabled_default(self, db_session_factory):
        await db_session_factory.create(name="only", base_url="https://x/v1", model="m")
        mgr = ProviderManager(db_session_factory)
        provider = await mgr.get_default()
        assert provider._model == "m"

    @pytest.mark.asyncio
    async def test_multiple_enabled_ambiguous(self, db_session_factory):
        await db_session_factory.create(name="a", base_url="https://x/v1", model="m1")
        await db_session_factory.create(name="b", base_url="https://x/v1", model="m2")
        mgr = ProviderManager(db_session_factory)
        with pytest.raises(AmbiguousDefaultProviderError, match="multiple enabled"):
            await mgr.get_default()

    @pytest.mark.asyncio
    async def test_disabled_not_counted(self, db_session_factory):
        await db_session_factory.create(name="a", base_url="https://x/v1", model="m1", enabled=True)
        await db_session_factory.create(name="b", base_url="https://x/v1", model="m2", enabled=False)
        mgr = ProviderManager(db_session_factory)
        provider = await mgr.get_default()  # only 'a' enabled -> OK
        assert provider._model == "m1"
