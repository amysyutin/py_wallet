import pytest

@pytest.fixture
def mock_spot_balance():
    return [
        {"asset": "BTC", "free": "0.001", "loked": "0.00000000"},
        {"asset": "USDT", "free": "100.00000000", "loked": "0.00000000"},
        {"asset": "XRP", "free":"0.00000000", "loked":"0.00000000"},
    ]


@pytest.fixture
def mock_prices():
    return {
        "BTC": 50000.0,
        "ETH": 3000.0,
        "USDT": 1.0,
        "BNB": 400.0
    }
