import os
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

import app.db.models  # noqa: F401
import app.routes as app_routes
from app.core.config import settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app.services.admin_promote import PromoteAdminStatus, promote_admin_by_email

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", settings.database_url)

# NullPool: новое соединение на каждый connect — без «залипания» на чужом loop
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: тесты, требующие реальных API")
    config.addinivalue_line("markers", "e2e: end-to-end тесты")


@pytest.fixture
def mock_spot_balance():
    return [
        {"asset": "BTC", "free": "0.001", "locked": "0.00000000"},
        {"asset": "USDT", "free": "100.00000000", "locked": "0.00000000"},
        {"asset": "XRP", "free": "0.00000000", "locked": "0.00000000"},
    ]


@pytest.fixture
def mock_prices():
    return {
        "BTCUSDT": 50000.0,
        "ETHUSDT": 3000.0,
        "BNBUSDT": 400.0,
    }


@pytest.fixture
def mock_spot_balances_raw():
    """Ответ Binance /api/v3/account balances — с нулевыми и ненулевыми."""
    return [
        {"asset": "BTC", "free": "0.1", "locked": "0.0"},
        {"asset": "USDT", "free": "100", "locked": "0.0"},
        {"asset": "XRP", "free": "0.0", "locked": "0.0"},
        {"asset": "ETH", "free": "0.0", "locked": "0.5"},
    ]


@pytest.fixture
def mock_earn_balances():
    return [
        {"asset": "ETH", "amount": 1.0},
        {"asset": "BNB", "amount": 2.5},
    ]


@pytest.fixture
def mock_full_prices():
    return {
        "BTCUSDT": 50000.0,
        "ETHUSDT": 3000.0,
        "BNBUSDT": 400.0,
        "USDCUSDT": 1.0,
        "USDT": 1.0,
    }


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    import asyncio

    original_health_engine = app_routes.engine
    app_routes.engine = test_engine

    async def _init():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())
    yield
    app_routes.engine = original_health_engine
    # dispose не вызываем через asyncio.run — иначе снова ломаем loop


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
