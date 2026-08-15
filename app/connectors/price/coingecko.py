from threading import Lock
from time import monotonic

import requests

from app.config import NATIVE_CG_ID

PRICE_CACHE_TTL_SECONDS = 300.0

ETH_USD_CACHE: float | None = None
ETH_USD_CACHE_UPDATED_AT: float | None = None
NATIVE_PRICE_CACHE: dict[str, float] = {}
NATIVE_PRICE_CACHE_UPDATED_AT: dict[str, float] = {}

_PRICE_CACHE_LOCK = Lock()


def _cache_is_fresh(updated_at: float | None, now: float) -> bool:
    return updated_at is not None and now - updated_at < PRICE_CACHE_TTL_SECONDS


def _fetch_price_usd(cg_id: str) -> float:
    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": cg_id, "vs_currencies": "usd"},
        timeout=15,
    )
    response.raise_for_status()
    price = float(response.json().get(cg_id, {}).get("usd", 0.0))
    if price <= 0:
        raise ValueError(f"CoinGecko returned an invalid USD price for {cg_id}")
    return price


def get_eth_usd_price_cached() -> float:
    global ETH_USD_CACHE, ETH_USD_CACHE_UPDATED_AT

    now = monotonic()
    if ETH_USD_CACHE is not None and _cache_is_fresh(ETH_USD_CACHE_UPDATED_AT, now):
        return ETH_USD_CACHE

    with _PRICE_CACHE_LOCK:
        now = monotonic()
        if ETH_USD_CACHE is not None and _cache_is_fresh(ETH_USD_CACHE_UPDATED_AT, now):
            return ETH_USD_CACHE
        try:
            price = _fetch_price_usd("ethereum")
        except Exception:
            if ETH_USD_CACHE is not None:
                return ETH_USD_CACHE
            raise
        ETH_USD_CACHE = price
        ETH_USD_CACHE_UPDATED_AT = now
        return price


def get_native_price_usd_cached(chain: str) -> float:
    cg_id = NATIVE_CG_ID.get(chain, "")
    if not cg_id:
        return 0.0
    return get_coin_price_usd_cached(cg_id)


def get_coin_price_usd_cached(cg_id: str) -> float:
    """Return a cached CoinGecko price for a canonical coin identifier."""
    if cg_id == "ethereum":
        return get_eth_usd_price_cached()
    now = monotonic()
    cached_price = NATIVE_PRICE_CACHE.get(cg_id)
    if cached_price is not None and _cache_is_fresh(
        NATIVE_PRICE_CACHE_UPDATED_AT.get(cg_id), now
    ):
        return cached_price

    with _PRICE_CACHE_LOCK:
        now = monotonic()
        cached_price = NATIVE_PRICE_CACHE.get(cg_id)
        if cached_price is not None and _cache_is_fresh(
            NATIVE_PRICE_CACHE_UPDATED_AT.get(cg_id), now
        ):
            return cached_price
        try:
            price = _fetch_price_usd(cg_id)
        except Exception:
            if cached_price is not None:
                return cached_price
            raise
        NATIVE_PRICE_CACHE[cg_id] = price
        NATIVE_PRICE_CACHE_UPDATED_AT[cg_id] = now
        return price


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
