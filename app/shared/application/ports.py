import asyncio
from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime:
        """Instante actual con zona horaria (UTC)."""


class TokenGenerator(ABC):
    @abstractmethod
    def new_token(self) -> str:
        """Token opaco, no adivinable y apto para URL."""


class UnitOfWork(ABC):
    """Frontera transaccional: los repositorios de una petición comparten la misma."""

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...


@dataclass(frozen=True)
class RealtimeEvent:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)


class RealtimePublisher(ABC):
    @abstractmethod
    async def publish(self, topic: str, event: RealtimeEvent) -> None:
        """Se llama siempre después del commit."""


class RealtimeSubscriber(ABC):
    @abstractmethod
    def subscribe(self, *topics: str) -> AbstractAsyncContextManager[asyncio.Queue[RealtimeEvent]]:
        """Una cola que recibe los eventos de todos los tópicos indicados mientras dure el contexto."""


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, key: str, limit: int, window_seconds: float) -> int | None:
        """Registra un intento. None si pasa; si no, los segundos que faltan para poder reintentar."""
