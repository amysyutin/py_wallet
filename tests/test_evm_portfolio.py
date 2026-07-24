"""Unit-тесты сервиса EVM-портфолио: summarize_chain, summarize_all."""

from unittest.mock import patch

import requests

from app.config import TOKENS_BY_CHAIN
from app.services.portfolio import summarize_chain, summarize_all

MODULE = "app.services.portfolio"


# ─── summarize_chain ────────────────────────────────────────────────────────


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=6)
@patch(f"{MODULE}.balance_of", return_value=0)
@patch(f"{MODULE}.get_balance", return_value=1_000_000_000_000_000_000)
def test_summarize_chain_mainnet(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    with patch(f"{MODULE}.CHAIN_RPC", {"mainnet": "https://rpc.fake"}):
        cs = summarize_chain("mainnet", "0xABC")
    assert cs.chain == "mainnet"
    assert cs.native_symbol == "ETH"
    assert cs.native_amount == 1.0
    assert cs.usdt_amount == 0.0
    assert cs.usdc_amount == 0.0
    assert cs.tokens == []


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=6)
@patch(f"{MODULE}.balance_of")
@patch(f"{MODULE}.get_balance", return_value=0)
def test_summarize_chain_with_stablecoins(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    # balance_of вызывается для USDT, USDC, и на bnb ещё для ETH
    # Для mainnet: USDT, USDC — 2 вызова
    mock_erc20_bal.side_effect = [
        500_000_000,
        250_000_000,
    ]  # 500 USDT, 250 USDC (6 decimals)
    with patch(f"{MODULE}.CHAIN_RPC", {"mainnet": "https://rpc.fake"}):
        cs = summarize_chain("mainnet", "0xABC")
    assert cs.usdt_amount == 500.0
    assert cs.usdc_amount == 250.0


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=18)
@patch(f"{MODULE}.balance_of")
@patch(f"{MODULE}.get_balance", return_value=5_000_000_000_000_000_000)
def test_summarize_chain_bnb_with_eth_token(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    # BNB chain: balance_of вызывается для USDT, USDC, ETH_token — 3 вызова
    # USDT=0, USDC=0, ETH=2e18 (2 ETH on BNB)
    mock_erc20_bal.side_effect = [0, 0, 2_000_000_000_000_000_000]
    with patch(f"{MODULE}.CHAIN_RPC", {"bnb": "https://rpc.fake"}):
        cs = summarize_chain("bnb", "0xABC")
    assert cs.chain == "bnb"
    assert cs.native_symbol == "BNB"
    assert cs.native_amount == 5.0
    assert len(cs.tokens) == 1
    assert cs.tokens[0].symbol == "ETH_on_bnb"
    assert cs.tokens[0].amount == 2.0
    assert cs.tokens[0].usd == 6000.0


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=18)
@patch(f"{MODULE}.balance_of", return_value=0)
@patch(f"{MODULE}.get_balance", return_value=0)
def test_summarize_chain_bnb_no_eth_token(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    """Если ETH on BNB баланс = 0, токен не добавляется."""
    cs = summarize_chain("bnb", "0xABC")
    assert cs.tokens == []


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=18)
@patch(f"{MODULE}.balance_of")
@patch(f"{MODULE}.get_balance", return_value=0)
def test_summarize_chain_distinguishes_binance_peg_usdc(
    _mock_get_bal, mock_erc20_bal, _mock_dec, _mock_eth_price
):
    mock_erc20_bal.side_effect = [0, 2_000_000_000_000_000_000, 0]

    with patch(f"{MODULE}.CHAIN_RPC", {"bnb": "https://rpc.fake"}):
        cs = summarize_chain("bnb", "0xABC")

    assert cs.usdc_amount == 0
    assert len(cs.tokens) == 1
    assert cs.tokens[0].symbol == "BINANCE_PEG_USDC"
    assert cs.tokens[0].amount == 2
    assert cs.tokens[0].usd == 2


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals", return_value=6)
@patch(f"{MODULE}.balance_of", return_value=0)
@patch(f"{MODULE}.get_balance", return_value=0)
def test_summarize_chain_no_rpc_url(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    """Цепочка без RPC URL → skipped summary без RPC/ERC-20 вызовов."""
    with patch(f"{MODULE}.CHAIN_RPC", {"test_chain": ""}):
        with patch(
            f"{MODULE}.TOKENS_BY_CHAIN",
            {
                "test_chain": {
                    "USDT": "0x0000000000000000000000000000000000000001",
                    "USDC": "0x0000000000000000000000000000000000000002",
                }
            },
        ):
            with patch(f"{MODULE}.NATIVE_SYMBOL", {"test_chain": "TEST"}):
                cs = summarize_chain("test_chain", "0xABC")
                assert cs.native_amount == 0.0
                assert cs.usdt_amount == 0.0
                assert cs.usdc_amount == 0.0
                assert cs.status == "skipped"
                assert cs.error_type == "missing_rpc_url"
                mock_get_bal.assert_not_called()
                mock_erc20_bal.assert_not_called()
                mock_dec.assert_not_called()


@patch(f"{MODULE}.get_eth_usd_price_cached", return_value=3000.0)
@patch(f"{MODULE}.decimals")
@patch(f"{MODULE}.balance_of")
@patch(f"{MODULE}.get_balance")
def test_summarize_chain_missing_address_skips_rpc_calls(
    mock_get_bal, mock_erc20_bal, mock_dec, mock_eth_price
):
    with patch(f"{MODULE}.CHAIN_RPC", {"mainnet": "https://rpc.fake"}):
        cs = summarize_chain("mainnet", "")

    assert cs.status == "skipped"
    assert cs.error_type == "missing_address"
    mock_get_bal.assert_not_called()
    mock_erc20_bal.assert_not_called()
    mock_dec.assert_not_called()


@patch(f"{MODULE}.get_balance", side_effect=requests.Timeout("slow RPC"))
def test_summarize_chain_timeout_isolated(_mock_get_balance):
    with patch(f"{MODULE}.CHAIN_RPC", {"base": "https://rpc.fake"}):
        cs = summarize_chain("base", "0xABC")

    assert cs.status == "timeout"
    assert cs.error_type == "timeout"
    assert cs.native_amount == 0


@patch(f"{MODULE}.get_balance")
def test_summarize_chain_does_not_expose_rpc_url(mock_get_balance):
    secret_url = "https://rpc.example/v2/PLACEHOLDER_API_KEY"
    mock_get_balance.side_effect = requests.HTTPError(
        f"unauthorized for url: {secret_url}"
    )

    with patch(f"{MODULE}.CHAIN_RPC", {"base": secret_url}):
        cs = summarize_chain("base", "0xABC")

    assert cs.error_message == "RPC request failed"
    assert "PLACEHOLDER_API_KEY" not in cs.error_message


@patch(f"{MODULE}.get_balance")
def test_summarize_chain_rate_limit_isolated(mock_get_balance):
    response = requests.Response()
    response.status_code = 429
    error = requests.HTTPError("rate limited", response=response)
    mock_get_balance.side_effect = error

    with patch(f"{MODULE}.CHAIN_RPC", {"base": "https://rpc.fake"}):
        cs = summarize_chain("base", "0xABC")

    assert cs.status == "rate_limited"
    assert cs.error_type == "rate_limited"


@patch(f"{MODULE}.decimals", return_value=6)
@patch(f"{MODULE}.balance_of", return_value=0)
@patch(f"{MODULE}.get_balance")
def test_summarize_chain_uses_next_rpc_after_failure(
    mock_get_balance, _mock_balance_of, _mock_decimals
):
    mock_get_balance.side_effect = [requests.Timeout("primary down"), 0]

    with patch(
        f"{MODULE}.CHAIN_RPC",
        {"base": "https://primary.fake, https://backup.fake"},
    ):
        cs = summarize_chain("base", "0xABC")

    assert cs.status == "success"
    assert [call.args[0] for call in mock_get_balance.call_args_list] == [
        "https://primary.fake",
        "https://backup.fake",
    ]


def test_native_usdc_contracts_match_issuer_registry():
    assert TOKENS_BY_CHAIN["mainnet"]["USDC"] == (
        "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
    )
    assert TOKENS_BY_CHAIN["base"]["USDC"] == (
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    )
    assert TOKENS_BY_CHAIN["arbitrum"]["USDC"] == (
        "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
    )
    assert TOKENS_BY_CHAIN["linea"]["USDC"] == (
        "0x176211869cA2b568f2A7D4EE941E073a821EE1ff"
    )


# ─── summarize_all ──────────────────────────────────────────────────────────


@patch(f"{MODULE}.get_native_price_usd_cached")
@patch(f"{MODULE}.summarize_chain")
def test_summarize_all_aggregates_chains(mock_chain, mock_price):
    from app.models import ChainSummary

    mock_price.return_value = 3000.0

    chain1 = ChainSummary(
        chain="mainnet",
        native_symbol="ETH",
        native_amount=1.0,
        usdt_amount=100.0,
        usdc_amount=50.0,
    )
    chain2 = ChainSummary(
        chain="base",
        native_symbol="ETH",
        native_amount=0.5,
        usdt_amount=0.0,
        usdc_amount=0.0,
    )
    mock_chain.side_effect = [chain1, chain2]

    with patch(f"{MODULE}.CHAIN_RPC", {"mainnet": "url1", "base": "url2"}):
        ps = summarize_all("0xABC")

    assert ps.address == "0xABC"
    assert len(ps.chains) == 2
    # chain1: 1.0*3000 + 100 + 50 = 3150
    # chain2: 0.5*3000 + 0 + 0 = 1500
    assert ps.total_usd == 4650.0


@patch(f"{MODULE}.get_native_price_usd_cached", return_value=3000.0)
@patch(f"{MODULE}.summarize_chain")
def test_summarize_all_includes_token_usd(mock_chain, mock_price):
    from app.models import ChainSummary, TokenBalance

    token = TokenBalance(symbol="ETH_on_bnb", amount=2.0, usd=6000.0)
    chain = ChainSummary(
        chain="bnb",
        native_symbol="BNB",
        native_amount=10.0,
        usdt_amount=0.0,
        usdc_amount=0.0,
        tokens=[token],
    )
    mock_chain.return_value = chain

    with patch(f"{MODULE}.CHAIN_RPC", {"bnb": "url"}):
        ps = summarize_all("0xABC")

    # 10.0 * 3000 + 0 + 0 + 6000 = 36000
    assert ps.total_usd == 36000.0


@patch(f"{MODULE}.get_native_price_usd_cached", return_value=0.0)
@patch(f"{MODULE}.summarize_chain")
def test_summarize_all_empty_chains(mock_chain, mock_price):
    with patch(f"{MODULE}.CHAIN_RPC", {}):
        ps = summarize_all("0xABC")
    assert ps.chains == []
    assert ps.total_usd == 0.0


@patch(f"{MODULE}.get_native_price_usd_cached")
def test_summarize_all_includes_skipped_chain_without_pricing(mock_price):
    with patch(f"{MODULE}.CHAIN_RPC", {"mainnet": ""}):
        ps = summarize_all("0xABC")

    assert len(ps.chains) == 1
    assert ps.chains[0].chain == "mainnet"
    assert ps.chains[0].status == "skipped"
    assert ps.chains[0].error_type == "missing_rpc_url"
    assert ps.total_usd == 0.0
    mock_price.assert_not_called()
