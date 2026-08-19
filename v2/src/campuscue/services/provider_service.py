"""ProviderService (M5) — ProviderConfig CRUD + test through the existing
Provider Foundation. No secrets are ever stored or returned.
"""

from __future__ import annotations

from campuscue.providers.errors import ProviderError
from campuscue.providers.manager import ProviderManager
from campuscue.repositories.repositories import ProviderConfigRepository
from campuscue.storage.models import ProviderConfig


class ProviderService:
    def __init__(self, configs: ProviderConfigRepository, manager: ProviderManager) -> None:
        self._configs = configs
        self._manager = manager

    async def list_providers(self) -> list[ProviderConfig]:
        return await self._configs.list_all()

    async def get_provider(self, provider_id: int) -> ProviderConfig:
        return await self._configs.get(provider_id)

    async def create_provider(
        self,
        *,
        name: str,
        base_url: str,
        model: str,
        provider_type: str = "openai_compatible",
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        timeout_s: float = 30.0,
        secret_reference: str | None = None,
        enabled: bool = True,
    ) -> ProviderConfig:
        return await self._configs.create(
            name=name,
            provider_type=provider_type,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_context_tokens=max_context_tokens,
            timeout_s=timeout_s,
            secret_reference=secret_reference,
            enabled=enabled,
        )

    async def update_provider(
        self,
        provider_id: int,
        *,
        name: str | None = None,
        provider_type: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_context_tokens: int | None = None,
        timeout_s: float | None = None,
        secret_reference: str | None = None,
        enabled: bool | None = None,
    ) -> ProviderConfig:
        return await self._configs.update(
            provider_id,
            name=name,
            provider_type=provider_type,
            base_url=base_url,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            max_context_tokens=max_context_tokens,
            timeout_s=timeout_s,
            secret_reference=secret_reference,
            enabled=enabled,
        )

    async def delete_provider(self, provider_id: int) -> None:
        await self._configs.delete(provider_id)

    async def test_provider(self, provider_id: int) -> dict:
        """Test one provider through the real Provider Foundation (no raw body)."""
        provider = await self._manager.get_by_id(provider_id)
        try:
            result = await provider.test()
            return {
                "ok": True,
                "latency_ms": result.get("latency_ms"),
                "error_category": None,
                "message": "provider test succeeded",
            }
        except ProviderError as e:
            return {
                "ok": False,
                "latency_ms": None,
                "error_category": e.code.value,
                "message": e.safe_message,
            }
