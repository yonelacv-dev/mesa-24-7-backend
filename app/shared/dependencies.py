"""Raíz de composición compartida: reloj, tokens, bus de tiempo real, límite de intentos y sesión."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_session, get_session_factory
from app.shared.application.errors import RateLimited
from app.shared.application.ports import (
    Clock,
    RateLimiter,
    RealtimePublisher,
    RealtimeSubscriber,
    TokenGenerator,
    UnitOfWork,
)
from app.shared.infrastructure.clock import SystemClock
from app.shared.infrastructure.realtime import InMemoryRealtimeBroker
from app.shared.infrastructure.tokens import SecretsTokenGenerator
from app.shared.infrastructure.unit_of_work import SQLAlchemyUnitOfWork

_CLOCK = SystemClock()
_TOKENS = SecretsTokenGenerator()


def get_clock() -> Clock:
    return _CLOCK


def get_tokens() -> TokenGenerator:
    return _TOKENS


def get_broker(request: Request) -> InMemoryRealtimeBroker:
    return request.app.state.broker


def get_publisher(broker: InMemoryRealtimeBroker = Depends(get_broker)) -> RealtimePublisher:
    return broker


def get_subscriber(broker: InMemoryRealtimeBroker = Depends(get_broker)) -> RealtimeSubscriber:
    return broker


def get_sse_heartbeat_seconds(request: Request) -> float:
    return request.app.state.settings.sse_heartbeat_seconds


def get_rate_limiter(request: Request) -> RateLimiter:
    return request.app.state.rate_limiter


def get_uow(session: AsyncSession = Depends(get_session)) -> UnitOfWork:
    return SQLAlchemyUnitOfWork(session)


def get_stream_session_factory() -> async_sessionmaker[AsyncSession]:
    """Los streams no pueden usar la sesión de la petición (vive lo que dura la conexión): abren sesiones cortas."""
    return get_session_factory()


def get_session_releaser(session: AsyncSession = Depends(get_session)) -> Callable[[], Awaitable[None]]:
    """Los endpoints de stream la llaman tras validar: la sesión de la petición no debe retener una conexión
    del pool durante toda la conexión SSE."""
    return session.close


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(name: str, limit: int, window_seconds: float) -> Callable:
    """Dependencia que limita los intentos por IP para una ruta."""

    async def dependency(request: Request, limiter: RateLimiter = Depends(get_rate_limiter)) -> None:
        retry_after = limiter.hit(f"{name}:{client_ip(request)}", limit, window_seconds)
        if retry_after is not None:
            raise RateLimited(retry_after)

    return dependency
