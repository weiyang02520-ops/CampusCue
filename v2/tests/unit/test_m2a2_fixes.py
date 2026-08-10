"""M2a.2 regression tests: shared numeric validation at persistence, request
override validation before transport, no hidden ORM wall-clock."""

from __future__ import annotations

import math

import httpx
import pytest

from campuscue.providers.models import LLMMessage, LLMRequest
from campuscue.providers.openai_compatible import OpenAICompatibleProvider


@pytest.fixture
async def db_session_factory_raw(tmp_path):
    from campuscue.storage.database import Database, DatabaseConfig

    database = Database(DatabaseConfig(path=tmp_path / "m2a2.db", env="test"))
    await database.initialize()
    yield database
    await database.dispose()


def _ok_response():
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "PONG"}}], "usage": {}})


def _provider_with(handler):
    return OpenAICompatibleProvider(
        base_url="https://api.example.com/v1/", model="m",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


# ------------------------------------------------------------------ B: repository numeric rejection

class TestRepositoryNumericRejection:
    @pytest.mark.asyncio
    async def test_timeout_invalid_rejected_before_persistence(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ProviderConfigRepository

        repo = ProviderConfigRepository(db_session_factory_raw.session)
        for bad in (0, -1, math.inf, math.nan):
            with pytest.raises(ValueError, match="timeout_s"):
                await repo.create(name=f"t{bad}", base_url="https://x/v1", model="m", timeout_s=bad)
        # prove nothing persisted
        assert await repo.list_enabled() == []

    @pytest.mark.asyncio
    async def test_max_tokens_invalid_rejected_before_persistence(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ProviderConfigRepository

        repo = ProviderConfigRepository(db_session_factory_raw.session)
        for bad in (0, -1, True):
            with pytest.raises(ValueError, match="max_tokens"):
                await repo.create(name=f"mt{bad}", base_url="https://x/v1", model="m", max_tokens=bad)
        assert await repo.list_enabled() == []

    @pytest.mark.asyncio
    async def test_max_context_tokens_invalid_rejected(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ProviderConfigRepository

        repo = ProviderConfigRepository(db_session_factory_raw.session)
        for bad in (0, -1, True):
            with pytest.raises(ValueError, match="max_context_tokens"):
                await repo.create(name=f"mct{bad}", base_url="https://x/v1", model="m", max_context_tokens=bad)
        assert await repo.list_enabled() == []

    @pytest.mark.asyncio
    async def test_temperature_invalid_rejected_before_persistence(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ProviderConfigRepository

        repo = ProviderConfigRepository(db_session_factory_raw.session)
        for bad in (-0.1, math.nan, math.inf, True):
            with pytest.raises(ValueError, match="temperature"):
                await repo.create(name=f"temp{bad}", base_url="https://x/v1", model="m", temperature=bad)
        assert await repo.list_enabled() == []

    @pytest.mark.asyncio
    async def test_valid_values_pass(self, db_session_factory_raw):
        from campuscue.repositories.repositories import ProviderConfigRepository

        repo = ProviderConfigRepository(db_session_factory_raw.session)
        cfg = await repo.create(
            name="ok", base_url="https://x/v1", model="m",
            timeout_s=10.0, max_tokens=100, max_context_tokens=4000, temperature=0.0,
        )
        assert cfg.id > 0


# ------------------------------------------------------------------ C: request override validation (no transport)

class TestRequestOverrideValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"max_tokens": -1}, {"max_tokens": 0}, {"max_tokens": True},
        {"temperature": -0.1}, {"temperature": math.nan}, {"temperature": math.inf},
        {"timeout_s": 0}, {"timeout_s": -5}, {"timeout_s": math.inf},
    ])
    async def test_invalid_override_rejected_no_transport(self, kwargs):
        called = []

        def handler(request: httpx.Request) -> httpx.Response:
            called.append(1)
            return _ok_response()

        p = _provider_with(handler)
        from campuscue.providers.errors import ProviderError, ProviderErrorCode

        with pytest.raises(ProviderError) as ei:
            await p.chat(LLMRequest(
                messages=[LLMMessage(role="user", content="hi")], model="m", **kwargs
            ))
        assert ei.value.code == ProviderErrorCode.INVALID_REQUEST
        assert called == []  # NO TRANSPORT CALL

    @pytest.mark.asyncio
    async def test_valid_overrides_still_transport(self):
        called = []

        def handler(request: httpx.Request) -> httpx.Response:
            called.append(1)
            return _ok_response()

        p = _provider_with(handler)
        await p.chat(LLMRequest(
            messages=[LLMMessage(role="user", content="hi")], model="m",
            max_tokens=10, temperature=0.5, timeout_s=8.0,
        ))
        assert called == [1]


# ------------------------------------------------------------------ D: no hidden ORM wall-clock

class TestNoHiddenWallClock:
    def test_models_have_no_wall_clock_defaults(self):
        import inspect
        import re

        from campuscue.storage import models as m

        src = inspect.getsource(m)
        assert "datetime.now" not in src, "storage/models.py must not read wall clock"
        assert "_utcnow" not in src, "dead _utcnow helper must be gone"

    @pytest.mark.asyncio
    async def test_orm_requires_timestamps_no_silent_fill(self, db_session_factory_raw):
        """Direct ORM insert without created_at must FAIL (no hidden default)."""
        from sqlalchemy.exc import IntegrityError
        from campuscue.storage.models import Source

        async with db_session_factory_raw.session() as s:
            s.add(Source(platform="onebot", conversation_id="x"))
            with pytest.raises(Exception):
                await s.commit()  # NOT NULL constraint on created_at -> fail, not silent fill
