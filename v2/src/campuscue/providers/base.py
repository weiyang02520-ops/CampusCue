"""BaseProvider (M2). No streaming, no tool system, no fallback chain."""

from __future__ import annotations

from abc import ABC, abstractmethod

from campuscue.providers.models import LLMRequest, LLMResponse


class BaseProvider(ABC):
    provider_type: str = "base"

    @property
    @abstractmethod
    def model(self) -> str:
        """Configured model identifier (safe to persist/log; never a secret).

        Business code (e.g. TaskExtractor) depends on BaseProvider.model and
        provider_type — never on private `_model` attributes of implementations
        (M2b.1.1 abstraction contract).
        """

    @abstractmethod
    async def chat(self, request: LLMRequest) -> LLMResponse:
        """One chat completion call. Raises ProviderError on failure."""

    @abstractmethod
    async def test(self) -> dict:
        """Minimal connectivity test. Returns safe status info."""
