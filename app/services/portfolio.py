import requests

from app.connectors.erc20 import balance_of, decimals
from app.config import CHAIN_RPC, NATIVE_SYMBOL, TOKENS_BY_CHAIN
from app.connectors.rpc import get_balance
from app.models import ChainSummary, PortfolioSummary, TokenBalance
from app.connectors.price.coingecko import (
    get_native_price_usd_cached,
    get_eth_usd_price_cached,
)


def _empty_chain_summary(
    chain: str,
    *,
    status: str,
    error_type: str,
    error_message: str,
) -> ChainSummary:
    return ChainSummary(
        chain=chain,
        native_symbol=NATIVE_SYMBOL.get(chain, "NATIVE"),
        native_amount=0.0,
        usdt_amount=0.0,
        usdc_amount=0.0,
        tokens=[],
        status=status,
        error_type=error_type,
        error_message=error_message,
    )


def _rpc_error_type(exc: Exception) -> str:
    if isinstance(exc, requests.Timeout):
        return "timeout"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        if exc.response.status_code == 429:
            return "rate_limited"
    return "rpc_error"


def _rpc_urls(value: str) -> tuple[str, ...]:
    return tuple(url.strip() for url in value.split(",") if url.strip())


def _collect_chain(chain: str, address: str, rpc_url: str) -> ChainSummary:
    native_wei = get_balance(rpc_url, address)
    native_amount = native_wei / 10**18

    tokens_cfg = TOKENS_BY_CHAIN.get(chain, {})
    usdt_c = tokens_cfg.get("USDT")
    usdc_c = tokens_cfg.get("USDC")

    usdt_amt = (
        (balance_of(rpc_url, usdt_c, address) / (10 ** decimals(rpc_url, usdt_c)))
        if usdt_c
        else 0.0
    )
    usdc_amt = (
        (balance_of(rpc_url, usdc_c, address) / (10 ** decimals(rpc_url, usdc_c)))
        if usdc_c
        else 0.0
    )

    tokens: list[TokenBalance] = []
    for symbol in ("USDbC", "USDC.e", "BINANCE_PEG_USDC"):
        contract = tokens_cfg.get(symbol)
        if contract is None:
            continue
        amount = balance_of(rpc_url, contract, address) / (
            10 ** decimals(rpc_url, contract)
        )
        if amount > 0:
            tokens.append(TokenBalance(symbol=symbol, amount=amount, usd=amount))

    if chain == "bnb":
        eth_token = "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"
        eth_atm = balance_of(rpc_url, eth_token, address) / (
            10 ** decimals(rpc_url, eth_token)
        )
        if eth_atm > 0:
            eth_usd = eth_atm * get_eth_usd_price_cached()
            tokens.append(
                TokenBalance(symbol="ETH_on_bnb", amount=eth_atm, usd=eth_usd)
            )

    return ChainSummary(
        chain=chain,
        native_symbol=NATIVE_SYMBOL.get(chain, "NATIVE"),
        native_amount=native_amount,
        usdt_amount=usdt_amt,
        usdc_amount=usdc_amt,
        tokens=tokens,
    )


def summarize_chain(chain: str, address: str) -> ChainSummary:
    rpc_urls = _rpc_urls(CHAIN_RPC.get(chain, ""))
    if not rpc_urls:
        return _empty_chain_summary(
            chain,
            status="skipped",
            error_type="missing_rpc_url",
            error_message=f"RPC URL is not configured for chain '{chain}'",
        )
    if not address:
        return _empty_chain_summary(
            chain,
            status="skipped",
            error_type="missing_address",
            error_message="Wallet address is empty",
        )

    last_error: Exception | None = None
    for rpc_url in rpc_urls:
        try:
            return _collect_chain(chain, address, rpc_url)
        except Exception as exc:
            last_error = exc

    assert last_error is not None
    return _empty_chain_summary(
        chain,
        status=_rpc_error_type(last_error),
        error_type=_rpc_error_type(last_error),
        # Provider exceptions commonly include the full RPC URL, including API
        # credentials embedded in its path or query string.
        error_message="RPC request failed",
    )


def summarize_all(address: str) -> PortfolioSummary:
    chains: list[ChainSummary] = []
    total_usd = 0.0
    for chain in CHAIN_RPC:
        cs = summarize_chain(chain, address)
        chains.append(cs)
        if cs.status != "success":
            continue
        try:
            native_usd = cs.native_amount * get_native_price_usd_cached(chain)
        except Exception:
            native_usd = 0.0
        usdt_usd = cs.usdt_amount
        usdc_usd = cs.usdc_amount
        tokens_usd = sum(t.usd for t in cs.tokens)
        total_usd += native_usd + usdc_usd + usdt_usd + tokens_usd
    return PortfolioSummary(address=address, chains=chains, total_usd=total_usd)
