import pytest


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
