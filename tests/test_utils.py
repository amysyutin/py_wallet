"""Unit-тесты чистых функций: _pad_addr_32 и Pydantic-модели."""

import pytest
from pydantic import ValidationError

from app.connectors.erc20 import _pad_addr_32
from app.models import TokenBalance, ChainSummary, PortfolioSummary

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
