# ruff: noqa: E402
# Test isolation variables must be validated before importing application modules.
import os
import re
from urllib.parse import urlsplit

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("JWT_SECRET", "ci-test-secret")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "TEST_DATABASE_URL is required; tests never fall back to DATABASE_URL"
    )
test_database_name = (urlsplit(TEST_DATABASE_URL).path or "").lstrip("/")
if re.search(r"(^|_)test($|_)", test_database_name.lower()) is None:
    raise RuntimeError(
        "TEST_DATABASE_URL database name must contain a standalone 'test' segment"
    )
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from collections.abc import AsyncGenerator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.db.models  # noqa: F401
import app.routes as app_routes
from app.core.config import get_settings
from app.db.base import Base
from app.db.models.snapshot_service import (
    ChainSnapshot,
    SNAPSHOT_SERVICE_ALEMBIC_VERSION_TABLE,
    SNAPSHOT_SERVICE_TABLE_NAMES,
    SnapshotBalanceSnapshot,
    SnapshotRun,
    WalletSnapshot,
)
from app.db.session import get_session
from app.main import app
from app.services.admin_promote import PromoteAdminStatus, promote_admin_by_email

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
snapshot_read_model_tables = [
    SnapshotRun.__table__,
    WalletSnapshot.__table__,
    ChainSnapshot.__table__,
    SnapshotBalanceSnapshot.__table__,
]
assert {table.name for table in snapshot_read_model_tables} == set(
    SNAPSHOT_SERVICE_TABLE_NAMES
)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: тесты, требующие реальных API")
    config.addinivalue_line("markers", "e2e: end-to-end тесты")


@pytest.fixture
def fresh_settings(monkeypatch):
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    import asyncio

    original_health_engine = app_routes.engine
    app_routes.engine = test_engine

    async def _reset_snapshot_read_models(*, create: bool) -> None:
        async with test_engine.begin() as connection:
            if create:
                await connection.run_sync(
                    lambda sync_connection: Base.metadata.create_all(
                        sync_connection,
                        tables=snapshot_read_model_tables,
                    )
                )
                await connection.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS "
                        f'"{SNAPSHOT_SERVICE_ALEMBIC_VERSION_TABLE}" '
                        "(version_num VARCHAR(32) PRIMARY KEY)"
                    )
                )
            else:
                await connection.run_sync(
                    lambda sync_connection: Base.metadata.drop_all(
                        sync_connection,
                        tables=snapshot_read_model_tables,
                    )
                )
                await connection.execute(
                    text(
                        f'DROP TABLE IF EXISTS "{SNAPSHOT_SERVICE_ALEMBIC_VERSION_TABLE}"'
                    )
                )

    try:
        # Snapshot-service owns these tables outside this Alembic chain. Remove
        # test-only copies before API downgrades so repeated runs stay safe.
        asyncio.run(_reset_snapshot_read_models(create=False))
        alembic_config = Config("alembic.ini")
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
        asyncio.run(_reset_snapshot_read_models(create=True))
        yield
    finally:
        asyncio.run(_reset_snapshot_read_models(create=False))
        app_routes.engine = original_health_engine


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await trans.rollback()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
async def auth_headers(client: AsyncClient) -> dict[str, str]:
    email = "test@example.com"
    password = "testpass123"
    await client.post("/auth/register", json={"email": email, "password": password})
    r = await client.post("/auth/login", json={"email": email, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(
    client: AsyncClient, db_session: AsyncSession
) -> dict[str, str]:
    email = "admin@example.com"
    password = "testpass123"
    await client.post("/auth/register", json={"email": email, "password": password})
    result = await promote_admin_by_email(db_session, email)
    assert result.status == PromoteAdminStatus.promoted
    r = await client.post("/auth/login", json={"email": email, "password": password})
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
