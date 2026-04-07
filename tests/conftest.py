import pytest


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
