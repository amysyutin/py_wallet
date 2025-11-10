from typing import List
from app.models import Asset
from app.services.portfolio import summarize_chain
from app.config import ADDRESS_EVM, CHAIN_RPC
from app.connectors.price.coingecko import get_native_price_usd_cached

if __name__ == "__main__":

    grand = 0.0
    for ch in CHAIN_RPC:
        cs = summarize_chain(ch, ADDRESS_EVM)
        parts = [

            f"{cs.chain}: {cs.native_symbol}={cs.native_amount}",
            f"USDT={cs.usdt_amount}",
            f"USDC={cs.usdc_amount}",
        ]
        eth_on_bnb = next((t.amount for t in cs.tokens if t.symbol=="ETH_on_bnb"), 0.0)
        if ch == "bnb" and eth_on_bnb:
            parts.append(f"ETH_on_bnb={eth_on_bnb}")

        native_usd = cs.native_amount * get_native_price_usd_cached(ch)
        row_total = native_usd + cs.usdc_amount + cs.usdt_amount + sum(t.usd for t in cs.tokens)
        grand += row_total

        parts.append(f"total_usd={row_total}")
        print(", ".join(parts))

    print("ALL_CHAINS_TOTAL_USD", grand)    







