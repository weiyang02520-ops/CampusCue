"""SourceService (M2a + M5 API) — business validation + source lifecycle.

No Web API / UI / permission DSL. Lookup by canonical identity (platform,
conversation_id) per ADR-012-C. M5 adds list/update/delete (soft-delete) so
Task/Extraction provenance stays valid.
"""

from __future__ import annotations

from campuscue.repositories.repositories import (
    DuplicateError,
    NotFoundError,
    SourceRepository,
)
from campuscue.storage.models import Source

_ALLOWED_PRIVACY_POLICIES = {"default"}


class SourceServiceError(Exception):
    pass


class SourceService:
    def __init__(self, sources: SourceRepository) -> None:
        self._sources = sources

    async def create_source(
        self,
        *,
        platform: str,
        conversation_id: str,
        name: str = "",
        enabled: bool = True,
        auto_extract: bool = True,
        context_window: int = 5,
        privacy_policy: str = "default",
    ) -> Source:
        self._validate_platform(platform)
        self._validate_conversation_id(conversation_id)
        self._validate_policy(privacy_policy)
        try:
            return await self._sources.create(
                platform=platform,
                conversation_id=conversation_id,
                name=name,
                enabled=enabled,
                auto_extract=auto_extract,
                context_window=context_window,
                privacy_policy=privacy_policy,
            )
        except DuplicateError:
            raise SourceServiceError(
                f"source already exists: ({platform}, {conversation_id})"
            ) from None

    async def list_sources(self) -> list[Source]:
        return await self._sources.list_all()

    async def get_source(self, source_id: int) -> Source:
        return await self._sources.get(source_id)

    async def update_source(
        self,
        source_id: int,
        *,
        name: str | None = None,
        enabled: bool | None = None,
        auto_extract: bool | None = None,
        context_window: int | None = None,
        privacy_policy: str | None = None,
    ) -> Source:
        if privacy_policy is not None:
            self._validate_policy(privacy_policy)
        return await self._sources.update(
            source_id,
            name=name,
            enabled=enabled,
            auto_extract=auto_extract,
            context_window=context_window,
            privacy_policy=privacy_policy,
        )

    async def delete_source(self, source_id: int) -> Source:
        """Soft-delete: the row is retained (deleted_at set, disabled) so
        existing Task/Extraction provenance FKs remain valid."""
        return await self._sources.soft_delete(source_id)

    async def enable(self, platform: str, conversation_id: str) -> Source:
        source = await self._require(platform, conversation_id)
        return await self._sources.update(source.id, enabled=True)

    async def disable(self, platform: str, conversation_id: str) -> Source:
        source = await self._require(platform, conversation_id)
        return await self._sources.update(source.id, enabled=False)

    async def set_auto_extract(self, platform: str, conversation_id: str, value: bool) -> Source:
        source = await self._require(platform, conversation_id)
        return await self._sources.update(source.id, auto_extract=value)

    async def get_by_identity(self, platform: str, conversation_id: str) -> Source | None:
        return await self._sources.get_by_identity(platform, conversation_id)

    async def _require(self, platform: str, conversation_id: str) -> Source:
        source = await self._sources.get_by_identity(platform, conversation_id)
        if source is None:
            raise SourceServiceError(
                f"source not found: ({platform}, {conversation_id})"
            )
        return source

    @staticmethod
    def _validate_platform(platform: str) -> None:
        if not platform or not platform.replace("_", "").isalnum():
            raise SourceServiceError(f"invalid platform: {platform!r}")

    @staticmethod
    def _validate_conversation_id(conversation_id: str) -> None:
        if not conversation_id or len(conversation_id) > 64:
            raise SourceServiceError(f"invalid conversation_id: {conversation_id!r}")

    @staticmethod
    def _validate_policy(policy: str) -> None:
        if policy not in _ALLOWED_PRIVACY_POLICIES:
            raise SourceServiceError(f"unsupported privacy_policy: {policy!r}")
