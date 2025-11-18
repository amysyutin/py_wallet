from turtle import position
from fastapi import Request
from pydantic_core.core_schema import bytes_schema
import requests, time, hmac, hashlib
from urllib.parse import urlencode
from app.config import BINANCE_API_KEY, BINANCE_API_SECRET, BINANCE_BASE_URL



#  time Binance 

_TIME_OFFSET_MS = 0

def ping() -> bool:
    r = requests.get(f"{BINANCE_BASE_URL}/api/v3/ping", timeout=10)
    return r.status_code == 200

def sync_server_time():
    global _TIME_OFFSET_MS
    r = requests.get(f"{BINANCE_BASE_URL}/api/v3/time", timeout=10)
    r.raise_for_status()
    _TIME_OFFSET_MS = r.json()["serverTime"] - int(time.time()*1000)
    

from requests.adapters import HTTPAdapter, Retry

_session = requests.Session()
_retry = Retry(
    total=3,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=False
)
_session.mount("https://", HTTPAdapter(max_retries=_retry))

#  sign GET

def _ts_ms() -> int:
    return int(time.time()*1000) + _TIME_OFFSET_MS

def signed_get(path: str, params: dict) -> requests.Response:
    p = {**params, "timestamp": _ts_ms(), "recvWindow": 10000}
    q = urlencode(p, doseq=True)
    sig = hmac.new(BINANCE_API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    return _session.get(f"{BINANCE_BASE_URL}{path}?{q}&signature={sig}", headers=headers, timeout=(5,30))

# accaunt balance

def get_account_balances_spot() -> list[dict]:
    try:
        r = signed_get("/api/v3/account", {})
        if r.status_code == 400 and r.text.find("Timestamp") != -1:
            sync_server_time(); 
            r = signed_get("/api/v3/account", {})
        r.raise_for_status()
        return r.json().get("balances", [])
    except requests.ReadTimeout:
        raise TimeoutError("Binance spot account request timed out")

#Добавить в app/connectors/exchange/binance.py две функции-обёртки с вашей signed_get,
#  собрать там суммы по активам (например totalAmount/amount).

def get_account_balances_earn() -> list[dict]:
    try:
        r = signed_get("/sapi/v1/simple-earn/flexible/position", {})
        if r.status_code == 400 and "Timestamp" in r.text:
            sync_server_time(); 
            r = signed_get("/sapi/v1/simple-earn/flexible/position", {})
        r.raise_for_status()

        print("FLEX RAW:", r.text[:800])

        data = r.json()

        if isinstance(data, dict):
            positions = data.get("rows", [])

        else:
            positions = data    

        by_asset: dict[str, float] = {}
        for p in positions:
            asset = p["asset"]
            amount = float(p.get("totalAmount", 0.0))
            if amount <= 0:
                continue
            by_asset[asset] = by_asset.get(asset, 0.0) + amount


        return [{"asset": a, "amount": amt} for a, amt in by_asset.items()]
    except requests.ReadTimeout:
        raise TimeoutError("Binance earn account request timed out")




def get_account_balances_earn_locked() -> list[dict]:
    try:
        r = signed_get("/sapi/v1/simple-earn/locked/position",{
            "current": 1,
            "size": 100,
        })
        if r.status_code == 400 and "Timestamp" in r.text:
            sync_server_time()
            r = signed_get("/sapi/v1/simple-earn/locked/position",{
                "current":1,
                "size": 100,
            })
        r.raise_for_status()
        print("FLEX RAW:", r.text[:800])

        data = r.json()


        if isinstance(data, dict):
            positions = data.get("rows", [])
        else:
            positions = data


        by_asset: dict[str, float] = {}
        for p in positions:
            asset = p["asset"]

            amount = float(p.get("totalAmount", 0.0))
            if amount <= 0:
                continue
            by_asset[asset] = by_asset.get(asset, 0.0) + amount


        return [{"asset": a, "amount": amt} for a, amt in by_asset.items()]


    except requests.ReadTimeout:
        raise TimeoutError("Binance earn loked request time out")                







#  filter non zero

def filter_nonzero(bals: list[dict]) -> list[dict]:
    out = []
    for b in bals:
        amt = float(b["free"]) + float(b["locked"])
        if amt > 0:
            out.append({"asset": b["asset"], "amount": amt})
    return out



