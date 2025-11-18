from app.connectors.erc20 import balance_of, decimals
from app.config import CHAIN_RPC, NATIVE_SYMBOL, TOKENS_BY_CHAIN
from app.connectors.rpc import get_balance
from app.models import ChainSummary, PortfolioSummary, TokenBalance
from app.connectors.price.coingecko import get_native_price_usd_cached, get_eth_usd_price_cached

def summarize_chain(chain: str, address: str) -> ChainSummary:
    rpc_url = CHAIN_RPC.get(chain, "")
    native_wei = get_balance(rpc_url, address) if rpc_url and address else 0
    native_amount = native_wei / 10**18

    # native_usd_price = get_native_price_usd_cached(chain)
    tokens_cfg = TOKENS_BY_CHAIN.get(chain, {})
    usdt_c = tokens_cfg.get("USDT"); usdc_c = tokens_cfg.get("USDC")

    usdt_amt = (balance_of(rpc_url, usdt_c, address) / (10 ** decimals(rpc_url, usdt_c))) if usdt_c else 0.0
    usdc_amt = (balance_of(rpc_url, usdc_c, address) / (10 ** decimals(rpc_url, usdc_c))) if usdc_c else 0.0


    tokens: list[TokenBalance] = []
    if chain == "bnb":
        eth_token = "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"
        eth_atm = (balance_of(rpc_url, eth_token, address) / (10**decimals(rpc_url, eth_token)))
        if eth_atm > 0:
            eth_usd = eth_atm * get_eth_usd_price_cached()
            tokens.append(TokenBalance(symbol="ETH_on_bnb", amount=eth_atm, usd=eth_usd))

    return ChainSummary(
        chain=chain,
        native_symbol=NATIVE_SYMBOL.get(chain, "NATIVE"),
        native_amount=native_amount,
        usdt_amount=usdt_amt,
        usdc_amount=usdc_amt,
        tokens=tokens,
    )


def summarize_all(address: str) -> PortfolioSummary:
    chains: list[ChainSummary] = []
    total_usd = 0.0
    for chain in CHAIN_RPC:
        cs = summarize_chain(chain, address)
        chains.append(cs)
        native_usd = cs.native_amount * get_native_price_usd_cached(chain)
        usdt_usd = cs.usdt_amount
        usdc_usd = cs.usdc_amount
        tokens_usd = sum(t.usd for t in cs.tokens)
        total_usd += native_usd + usdc_usd + usdt_usd + tokens_usd
    return PortfolioSummary(address=address, chains=chains, total_usd=total_usd)    
