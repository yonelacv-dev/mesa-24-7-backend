from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models_registry  # noqa: F401  (registra los modelos ORM)
from app.auth.presentation.router import router as auth_router
from app.config import Settings, get_settings
from app.database import get_engine
from app.error_handling import register_exception_handlers
from app.shared.infrastructure.rate_limit import SlidingWindowRateLimiter
from app.shared.infrastructure.realtime import InMemoryRealtimeBroker
from app.venues.presentation.diner_router import router as venues_diner_router
from app.venues.presentation.host_router import router as venues_host_router
from app.waitlist.presentation.diner_router import router as waitlist_diner_router
from app.waitlist.presentation.host_router import router as waitlist_host_router

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await get_engine().dispose()

    app = FastAPI(
        title="Lista de espera digital",
        version="0.1.0",
        description=(
            "Las rutas cuelgan de `/venues/{slug}` y dicen a quién sirven: `/diner` (comensal, sin login) "
            "o `/host` (anfitrión, con `Authorization: Bearer`)."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.broker = InMemoryRealtimeBroker()
    app.state.rate_limiter = SlidingWindowRateLimiter(enabled=settings.rate_limit_enabled)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)

    for router in (auth_router, venues_diner_router, venues_host_router, waitlist_diner_router, waitlist_host_router):
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/health", tags=["ops"], summary="El servicio está vivo")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
