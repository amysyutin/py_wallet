"""Unit-тесты сервиса summarize_binance_usdt — основные сценарии и граничные случаи."""

from unittest.mock import patch
from app.services.binance_portfolio import summarize_binance_usdt

MODULE = "app.services.binance_portfolio"


def _patch_all(**overrides):
    """Хелпер: создаёт стандартный набор моков для summarize_binance_usdt."""
    defaults = {
        "sync_server_time": None,
        "spot": [
            {"asset": "BTC", "free": "0.1", "locked": "0.0"},
            {"asset": "USDT", "free": "100", "locked": "0.0"},
        ],
        "earn": [{"asset": "ETH", "amount": 1.0}],
        "earn_locked": [],
        "prices": {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 3000.0,
            "BNBUSDT": 400.0,
            "USDT": 1.0,
        },
    }
    defaults.update(overrides)

    def decorator(func):
        @patch(f"{MODULE}.load_all_price_cached", return_value=defaults["prices"])
        @patch(
            f"{MODULE}.get_account_balances_earn_locked",
            return_value=defaults["earn_locked"],
        )
        @patch(f"{MODULE}.get_account_balances_earn", return_value=defaults["earn"])
        @patch(f"{MODULE}.get_account_balances_spot", return_value=defaults["spot"])
        @patch(f"{MODULE}.sync_server_time")
        def wrapper(
            mock_sync, mock_spot, mock_earn, mock_locked, mock_prices, *args, **kwargs
        ):
            return func(
                mock_sync,
                mock_spot,
                mock_earn,
                mock_locked,
                mock_prices,
                *args,
                **kwargs,
            )

        wrapper.__name__ = func.__name__
        wrapper.__qualname__ = func.__qualname__
        return wrapper

    return decorator


# ─── Основные сценарии (из оригинальных тестов) ─────────────────────────────


@_patch_all()
def test_summarize_binance_usdt_success(
    mock_sync, mock_spot, mock_earn, mock_locked, mock_prices
):
    result = summarize_binance_usdt()

    assert "assets" in result
    assert "total_usdt" in result

    # 0.1 BTC * 50000 = 5000, 100 USDT = 100, 1.0 ETH * 3000 = 3000 → 8100
    assert result["total_usdt"] == 8100.0

    assets = {item["asset"]: item for item in result["assets"]}
    assert assets["BTC"]["source"] == "spot"
    assert assets["ETH"]["source"] == "earn_flexible"


def test_summarize_binance_usdt_timeout():
    with patch(f"{MODULE}.sync_server_time") as mock_sync:
        mock_sync.side_effect = TimeoutError("Connection failed")
        result = summarize_binance_usdt()
        assert result["error"] == "Connection failed"
        assert result["total_usdt"] == 0.0
        assert result["assets"] == []


# ─── Граничные случаи ───────────────────────────────────────────────────────


@_patch_all(
    spot=[{"asset": "BTC", "free": "0.0", "locked": "0.0"}],
    earn=[],
    earn_locked=[],
)
def test_all_balances_zero(mock_sync, mock_spot, mock_earn, mock_locked, mock_prices):
    result = summarize_binance_usdt()
    assert result["total_usdt"] == 0.0
    assert result["assets"] == []


@_patch_all(
    spot=[{"asset": "SHIB", "free": "1000000", "locked": "0.0"}],
    earn=[{"asset": "DOGE", "amount": 500.0}],
    earn_locked=[],
    prices={"SHIBUSDT": 0.00001, "DOGEUSDT": 0.1},
)
def test_unknown_assets_ignored(
    mock_sync, mock_spot, mock_earn, mock_locked, mock_prices
):
    """Активы вне important_assets (BTC, ETH, BNB, USDT, USDC) игнорируются."""
    result = summarize_binance_usdt()
    assert result["total_usdt"] == 0.0
    assert result["assets"] == []


@_patch_all(
    spot=[],
    earn=[{"asset": "LDUSDT", "amount": 200.0}, {"asset": "LDETH", "amount": 0.5}],
    earn_locked=[],
    prices={"ETHUSDT": 3000.0},
)
def test_alias_mapping(mock_sync, mock_spot, mock_earn, mock_locked, mock_prices):
    """LDUSDT → USDT, LDETH → ETH через alias_map."""
    result = summarize_binance_usdt()
    assets = {item["asset"]: item for item in result["assets"]}
    assert "USDT" in assets
    assert assets["USDT"]["original_asset"] == "LDUSDT"
    assert "ETH" in assets
    assert assets["ETH"]["original_asset"] == "LDETH"
    # 200 USDT + 0.5 ETH * 3000 = 1700
    assert result["total_usdt"] == 1700.0


@_patch_all(
    spot=[],
    earn=[],
    earn_locked=[{"asset": "BNB", "amount": 10.0}],
    prices={"BNBUSDT": 400.0},
)
def test_earn_locked_included(
    mock_sync, mock_spot, mock_earn, mock_locked, mock_prices
):
    """Активы из earn_locked учитываются в итоговой сумме."""
    result = summarize_binance_usdt()
    assert result["total_usdt"] == 4000.0
    assets = {item["asset"]: item for item in result["assets"]}
    assert assets["BNB"]["source"] == "earn_loked"


@_patch_all(
    spot=[{"asset": "BTC", "free": "0.001", "locked": "0.0"}],
    earn=[],
    earn_locked=[],
    prices={"BTCUSDT": 1.0},
)
def test_tiny_usd_value_format(
    mock_sync, mock_spot, mock_earn, mock_locked, mock_prices
):
    """Если usd < 0.01, usdt_str отображается как '<0.01'."""
    result = summarize_binance_usdt()
    btc = next(a for a in result["assets"] if a["asset"] == "BTC")
    assert btc["usdt_str"] == "<0.01"


@_patch_all(
    spot=[{"asset": "BTC", "free": "0.5", "locked": "0.0"}],
    earn=[{"asset": "BTC", "amount": 0.3}],
    earn_locked=[{"asset": "BTC", "amount": 0.2}],
    prices={"BTCUSDT": 50000.0},
)
def test_same_asset_multiple_sources(
    mock_sync, mock_spot, mock_earn, mock_locked, mock_prices
):
    """Один актив из разных источников — все строки попадают в результат."""
    result = summarize_binance_usdt()
    btc_rows = [a for a in result["assets"] if a["asset"] == "BTC"]
    assert len(btc_rows) == 3
    sources = {r["source"] for r in btc_rows}
    assert sources == {"spot", "earn_flexible", "earn_loked"}
    # 0.5 * 50000 + 0.3 * 50000 + 0.2 * 50000 = 50000
    assert result["total_usdt"] == 50000.0


@_patch_all(
    spot=[{"asset": "USDC", "free": "250", "locked": "0.0"}],
    earn=[],
    earn_locked=[],
    prices={"USDCUSDT": 1.0},
)
def test_usdc_supported(mock_sync, mock_spot, mock_earn, mock_locked, mock_prices):
    """USDC входит в important_assets и конвертируется."""
    result = summarize_binance_usdt()
    assert result["total_usdt"] == 250.0
    assert result["assets"][0]["asset"] == "USDC"
