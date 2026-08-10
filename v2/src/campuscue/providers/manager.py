"""Minimal ProviderManager (M2).

Default rule (ADR-012-E): exactly one ENABLED provider.
  0 -> NoProviderConfiguredError
  >1 -> AmbiguousDefaultProviderError
No silent first-row selection. No hot reload / fallback / scoring.
"""

from __future__ import annotations

from campuscue.providers.errors import (
    AmbiguousDefaultProviderError,
    NoProviderConfiguredError,
)
from campuscue.providers.models import LLMRequest, LLMResponse
from campuscue.providers.openai_compatible import OpenAICompatibleProvider
from campuscue.repositories.repositories import ProviderConfigRepository
from campuscue.storage.models import ProviderConfig


class ProviderManager:
    def __init__(self, configs: ProviderConfigRepository) -> None:
        self._configs = configs

    async def get_default(self) -> OpenAICompatibleProvider:
        enabled = await self._configs.list_enabled()
        if not enabled:
            raise NoProviderConfiguredError()
        if len(enabled) > 1:
            raise AmbiguousDefaultProviderError(len(enabled))
        return self._instantiate(enabled[0])

    def _instantiate(self, cfg: ProviderConfig) -> OpenAICompatibleProvider:
        if cfg.provider_type != "openai_compatible":
            raise ValueError(f"unsupported provider_type: {cfg.provider_type!r}")
        return OpenAICompatibleProvider(
            base_url=cfg.base_url,
            model=cfg.model,
            secret_reference=cfg.secret_reference,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            max_context_tokens=cfg.max_context_tokens,
            timeout_s=cfg.timeout_s,
        )

    async def test_default(self) -> dict:
        provider = await self.get_default()
        return await provider.test()
