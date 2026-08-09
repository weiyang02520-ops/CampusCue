"""PlatformAdapter boundary (M1: OneBotAdapter only).

Deliberately small: start / stop / send / status. No registry, no multi-platform
manager, no metadata ecosystem (deliberate divergence from AstrBot Platform).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from campuscue.core.outbound import OutgoingMessage


class PlatformAdapter(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None: ...

    @abstractmethod
    def status(self) -> dict: ...
