

import requests
from app.config import COINGECKO_PLATFORM, TOKENS_BY_CHAIN, NATIVE_CG_ID

ETH_USD_CACHE: float | None = None
NATIVE_PRICE_CACHE: dict[str, float] = {}



def get_eth_usd_price_cached() -> float:
    global ETH_USD_CACHE
    if ETH_USD_CACHE is None:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
        params={"ids":"ethereum","vs_currencies":"usd"}, timeout=15)
        r.raise_for_status()
        ETH_USD_CACHE = float(r.json().get("ethereum",{}).get("usd", 0.0))
    return ETH_USD_CACHE    


def get_native_price_usd_cached(chain: str) -> float:
    cg_id = NATIVE_CG_ID.get(chain, "")
    if not cg_id:
        return 0.0
    if cg_id == "ethereum":
        return get_eth_usd_price_cached()
    if cg_id in NATIVE_PRICE_CACHE:
        return NATIVE_PRICE_CACHE[cg_id]
    try:
        r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": cg_id, "vs_currencies": "usd"}, timeout=15)  
        r.raise_for_status()
        NATIVE_PRICE_CACHE[cg_id] = float(r.json().get(cg_id, {}).get("usd", 0.0))
    except Exception:
        NATIVE_PRICE_CACHE[cg_id] = 0.0
    return NATIVE_PRICE_CACHE[cg_id]         



# def get_token_prices_usd(chain: str, contracts: list[str]) -> dict[str, float]:
#     plat = COINGECKO_PLATFORM.get(chain, "")
#     if not plat or not contracts:
#         return {}
#     url = f"https://api.coingecko.com/api/v3/simple/token_price/{plat}"
#     r = requests.get(url, params={"contract_addresses": ",".join([c.lower() for c in contracts]), "vs_currencies": "usd"}, timeout=15)
#     print("cg:", r.status_code, r.url)
#     if r.status_code != 200:
#         return {}
#     data = r.json()
#     return {k.lower(): float(v.get("usd", 0.0)) for k, v in data.items()}

# # price eth to usd
# def get_eth_usd_price() -> float:
#     r = requests.get("https://api.coingecko.com/api/v3/simple/price",
#                     params={"ids":"ethereum","vs_currencies":"usd"}, timeout=15) 
#     r.raise_for_status()
#     data = r.json()
#     return float(data.get("ethereum",{}).get("usd", 0.0))  