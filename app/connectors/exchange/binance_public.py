import time, requests
from app.config import BINANCE_BASE_URL

_PRICES = {"data": None, "ts": 0}

def load_all_price_cached(ttl: int = 30) -> dict[str, float]:
    now = time.time()
    if _PRICES["data"] and now - _PRICES["ts"] < ttl:
        return _PRICES["data"]
    r = requests.get(f"{BINANCE_BASE_URL}/api/v3/ticker/price", timeout=15)
    r.raise_for_status()
    data = {x["symbol"]: float(x["price"]) for x in r.json()}
    _PRICES["data"], _PRICES["ts"] = data, now
    return data

def to_usdt(asset: str, amount: float, prices: dict[str, float]) -> float:
    if asset.upper() == "USDT": return amount
    return amount * prices.get(f"{asset.upper()}USDT", 0.0)


    


