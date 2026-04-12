"""Unit-тесты чистых функций: to_usdt, filter_nonzero, _pad_addr_32, Pydantic-модели."""

import pytest
from pydantic import ValidationError

from app.connectors.exchange.binance_public import to_usdt
from app.connectors.exchange.binance import filter_nonzero
from app.connectors.erc20 import _pad_addr_32
from app.models import TokenBalance, ChainSummary, PortfolioSummary


# ─── to_usdt ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "asset, amount, prices, expected",
    [
        ("BTC", 1.0, {"BTCUSDT": 60000.0}, 60000.0),
        ("BTC", 0.5, {"BTCUSDT": 60000.0}, 30000.0),
        ("ETH", 2.0, {"ETHUSDT": 3000.0}, 6000.0),
        ("USDT", 500.0, {}, 500.0),
        ("USDT", 0.0, {}, 0.0),
        ("DOGE", 100.0, {}, 0.0),
        ("UNKNOWN", 1.0, {"BTCUSDT": 60000.0}, 0.0),
    ],
)
def test_to_usdt(asset, amount, prices, expected):
    assert to_usdt(asset, amount, prices) == expected


def test_to_usdt_case_insensitive():
    prices = {"ETHUSDT": 3000.0}
    assert to_usdt("eth", 1.0, prices) == 3000.0
    assert to_usdt("Eth", 1.0, prices) == 3000.0


def test_to_usdt_usdt_ignores_prices():
    """USDT всегда 1:1, даже если в prices есть что-то другое."""
    assert to_usdt("USDT", 42.0, {"BTCUSDT": 99999.0}) == 42.0
    assert to_usdt("usdt", 42.0, {}) == 42.0


# ─── filter_nonzero ─────────────────────────────────────────────────────────


def test_filter_nonzero_basic(mock_spot_balance):
    result = filter_nonzero(mock_spot_balance)
    assets = [r["asset"] for r in result]
    assert "BTC" in assets
    assert "USDT" in assets
    assert "XRP" not in assets


def test_filter_nonzero_empty():
    assert filter_nonzero([]) == []


def test_filter_nonzero_all_zero():
    bals = [
        {"asset": "A", "free": "0.0", "locked": "0.0"},
        {"asset": "B", "free": "0.00000000", "locked": "0.00000000"},
    ]
    assert filter_nonzero(bals) == []


def test_filter_nonzero_locked_counts():
    """Если free=0, но locked > 0 — актив должен попасть в результат."""
    bals = [{"asset": "ETH", "free": "0.0", "locked": "0.5"}]
    result = filter_nonzero(bals)
    assert len(result) == 1
    assert result[0]["asset"] == "ETH"
    assert result[0]["amount"] == 0.5


def test_filter_nonzero_sums_free_and_locked():
    bals = [{"asset": "BTC", "free": "0.3", "locked": "0.2"}]
    result = filter_nonzero(bals)
    assert result[0]["amount"] == pytest.approx(0.5)


# ─── _pad_addr_32 ───────────────────────────────────────────────────────────


def test_pad_addr_32_length():
    result = _pad_addr_32("0xdAC17F958D2ee523a2206206994597C13D831ec7")
    assert result.startswith("0x")
    assert len(result) == 66


def test_pad_addr_32_lowercase():
    result = _pad_addr_32("0xABCDEF1234567890abcdef1234567890ABCDEF12")
    assert result == result.lower() or result[2:] == result[2:].lower()


def test_pad_addr_32_padding():
    addr = "0x1234567890abcdef12345678901234567890abcd"
    result = _pad_addr_32(addr)
    assert result[2:26] == "0" * 24
    assert result[26:] == addr[2:].lower()


# ─── Pydantic модели ────────────────────────────────────────────────────────


def test_token_balance_valid():
    tb = TokenBalance(symbol="ETH", amount=1.5, usd=4500.0)
    assert tb.symbol == "ETH"
    assert tb.amount == 1.5
    assert tb.usd == 4500.0


def test_chain_summary_defaults():
    cs = ChainSummary(
        chain="mainnet",
        native_symbol="ETH",
        native_amount=1.0,
        usdt_amount=0.0,
        usdc_amount=0.0,
    )
    assert cs.tokens == []


def test_chain_summary_with_tokens():
    token = TokenBalance(symbol="ETH_on_bnb", amount=0.5, usd=1500.0)
    cs = ChainSummary(
        chain="bnb",
        native_symbol="BNB",
        native_amount=10.0,
        usdt_amount=100.0,
        usdc_amount=50.0,
        tokens=[token],
    )
    assert len(cs.tokens) == 1
    assert cs.tokens[0].symbol == "ETH_on_bnb"


def test_portfolio_summary_valid():
    cs = ChainSummary(
        chain="mainnet",
        native_symbol="ETH",
        native_amount=1.0,
        usdt_amount=0.0,
        usdc_amount=0.0,
    )
    ps = PortfolioSummary(address="0xABC", chains=[cs], total_usd=3000.0)
    assert ps.address == "0xABC"
    assert len(ps.chains) == 1


def test_portfolio_summary_missing_field():
    with pytest.raises(ValidationError):
        PortfolioSummary(address="0xABC", chains=[])
