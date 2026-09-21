"""Pruebas contra MySQL real. Recrean `waiting_list_test` desde las migraciones y se saltan si MySQL no está."""

import asyncio
from pathlib import Path

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.config import Settings
from app.database import Base, get_session
from app.main import create_app
from app.shared.dependencies import get_clock, get_stream_session_factory
from tests.integration.support import Db

TEST_DATABASE = "waiting_list_test"
ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(items):
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    settings = Settings(mysql_database=TEST_DATABASE, _env_file=None)
    assert settings.mysql_database.endswith("_test")  # nunca se recrea otra base
    server_url = settings.database_url.replace(f"/{TEST_DATABASE}?", "/?")

    async def recreate() -> None:
        engine = create_async_engine(server_url, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE}"))
            await conn.execute(
                text(f"CREATE DATABASE {TEST_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
            )
        await engine.dispose()

    try:
        asyncio.run(recreate())
    except Exception as error:  # noqa: BLE001
        pytest.skip(f"MySQL no está disponible: {error}")

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(config, "head")
    return settings.database_url


@pytest.fixture
async def db(test_database_url):
    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    yield Db(engine)
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in Base.metadata.sorted_tables:
            await conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    await engine.dispose()


@pytest.fixture
async def make_client(db):
    """Cliente HTTP sobre la app real (ASGI), con la base de pruebas y el reloj de la prueba."""
    clients = []

    def build(rate_limit: bool = False) -> httpx.AsyncClient:
        settings = Settings(
            mysql_database=TEST_DATABASE, rate_limit_enabled=rate_limit, sse_heartbeat_seconds=0.05, _env_file=None
        )
        app = create_app(settings)

        async def session_override():
            async with db.factory() as session:
                yield session

        app.dependency_overrides[get_session] = session_override
        app.dependency_overrides[get_clock] = lambda: db.clock
        app.dependency_overrides[get_stream_session_factory] = lambda: db.factory
        app.state.broker = db.broker  # el mismo bus que ven las pruebas
        client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield build
    for client in clients:
        await client.aclose()


@pytest.fixture
async def client(make_client) -> httpx.AsyncClient:
    return make_client()
