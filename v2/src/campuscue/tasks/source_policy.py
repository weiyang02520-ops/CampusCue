"""L0 SourcePolicy (M2b.1).

M2 automatic extraction applies to GROUP messages only. For a group CampusEvent,
resolve the Source by (platform, conversation_id) and pass only when the source
exists AND enabled AND auto_extract. Unconfigured sources are never auto-created.
"""

from __future__ import annotations

from campuscue.core.events import CampusEvent, ConversationType
from campuscue.repositories.repositories import SourceRepository
from campuscue.storage.models import Source
from campuscue.tasks.models import SourcePolicyResult


class SourcePolicy:
    def __init__(self, sources: SourceRepository) -> None:
        self._sources = sources

    async def evaluate(self, event: CampusEvent) -> SourcePolicyResult:
        if event.conversation_type != ConversationType.GROUP:
            return SourcePolicyResult(allowed=False, reason="unsupported_conversation_type")
        source = await self._sources.get_by_identity(event.platform, event.conversation_id)
        if source is None:
            return SourcePolicyResult(allowed=False, reason="source_not_configured")
        if not source.enabled:
            return SourcePolicyResult(allowed=False, reason="source_disabled")
        if not source.auto_extract:
            return SourcePolicyResult(allowed=False, reason="auto_extract_disabled")
        return SourcePolicyResult(allowed=True)
