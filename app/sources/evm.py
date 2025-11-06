from typing import List
from app.models import Asset
import requests
from app.config import ADDRESS_EVM, RPC_URL_MAIN, CHAIN_RPC


#. DEBUG
# def get_eth_balance_via_rpc(address: str) -> tuple[int, float]:
#     # Получаю баланс eth через rpc-запрос
#     url_main = RPC_URL_MAIN
#     if not url_main:
#         print("RPC_URL пуст")
#         return (0, 0.0)    

#     if not address:
#         print("Пустой address - не передан адрес кошелька")
#         return (0, 0.0)

#     payload = {
#         "jsonrpc":"2.0",
#         "method":"eth_getBalance",
#         "params":[address,"latest"],
#         "id":1
#         }

#     try:
#         r = requests.post(url_main, json=payload, timeout=15)
#         r.raise_for_status() #if status 4xx/5xx
#         data = r.json()
#         if "error" in data or "result" not in data:
#             print(f"Ошибка RPC: {data}")
#             return (0, 0.0)
#         wei = int(data["result"], 16)
#         return wei, wei / 10**18
#     except Exception as e:
#         print(f"Ошибка при запросе RPC: {e}")
#         return (0, 0.0)


def get_native_eth_balance(chain: str, address: str) -> tuple[int, float]:
    from app.config import CHAIN_RPC
    url = CHAIN_RPC.get(chain, "")
    if not url or not address:
        return (0, 0.0)
    payload = {"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1} 
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json()
    wei = int(data.get("result","0x0"), 16)
    return wei, wei / 10**18 

# price eth to usd
def get_eth_usd_price() -> float:
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                    params={"ids":"ethereum","vs_currencies":"usd"}, timeout=15) 
    r.raise_for_status()
    data = r.json()
    return float(data.get("ethereum",{}).get("usd", 0.0))  


from app.config import NATIVE_CG_ID
def get_native_price_usd(chain: str) -> float:
    cg_id = NATIVE_CG_ID.get(chain, "")
    if not cg_id:
        return 0.0
    r = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": cg_id, "vs_currencies": "usd"},
        timeout=15
    )
    if r.status_code != 200:
        return 0.0
    return float(r.json().get(cg_id, {}).get("usd", 0.0))   


    
from app.config import NATIVE_SYMBOL
def _assets_native_usd(address: str) -> List[Asset]:
    assets, total = [], 0.0
    for chain in CHAIN_RPC:
        _, amount_native = get_native_eth_balance(chain, address)
        price_usd = get_native_price_usd_cached(chain)
        usd = amount_native * price_usd
        total += usd
        symbol = NATIVE_SYMBOL.get(chain, "NATIVE")
        assets.append(Asset(name=f"{symbol}:{chain}", price=usd, source="evm-rpc"))
    assets.append(Asset(name="TOTAL_USD", price=total, source="evm-rpc"))
    return assets

async def get_evm_balances(address: str) -> List[Asset]:
    if not address:
        from app.config import ADDRESS_EVM
        address = ADDRESS_EVM

    return _assets_native_usd(address)



from app.config import COINGECKO_PLATFORM, TOKENS_BY_CHAIN


def get_token_prices_usd(chain: str, contracts: list[str]) -> dict[str, float]:
    plat = COINGECKO_PLATFORM.get(chain, "")
    if not plat or not contracts:
        return {}
    url = f"https://api.coingecko.com/api/v3/simple/token_price/{plat}"
    r = requests.get(url, params={"contract_addresses": ",".join([c.lower() for c in contracts]), "vs_currencies": "usd"}, timeout=15)
    print("cg:", r.status_code, r.url)
    if r.status_code != 200:
        return {}
    data = r.json()
    return {k.lower(): float(v.get("usd", 0.0)) for k, v in data.items()}

def list_known_tokens_with_usd(chain: str, address: str) -> list[tuple[str, float, float]]:
    tokens = TOKENS_BY_CHAIN.get(chain, {})
    if not tokens:
        return []
    contracts = [c for c in tokens.values()]
    prices = get_token_prices_usd(chain, contracts)
    out = []
    for symbol, contract in tokens.items():
        bal = erc20_balance_of(CHAIN_RPC[chain], contract, address)
        if bal <= 0:
            continue
        dec = erc20_decimals(CHAIN_RPC[chain], contract) or 18
        amount = bal / (10**dec)
        usd = amount * prices.get(contract.lower(), 0.0)
        out.append((symbol, amount, usd))
    return out



ETH_USD_CACHE = None

def get_eth_usd_price_cached() -> float:
    global ETH_USD_CACHE
    if ETH_USD_CACHE is None:
        ETH_USD_CACHE = get_eth_usd_price()
    return ETH_USD_CACHE    


NATIVE_PRICE_CACHE = {}

def get_native_price_usd_cached(chain: str) -> float:
    from app.config import NATIVE_CG_ID
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

        



def summarize_chain(chain: str, address: str) -> dict:

    _, native_amt = get_native_eth_balance(chain, address)
    native_price = get_native_price_usd_cached(chain)
    native_usd = native_amt * native_price
    # стейблы цена = 1
    tokens = TOKENS_BY_CHAIN.get(chain, {})
    usdt_c = tokens.get("USDT"); usdc_c = tokens.get("USDC")
    usdt_amt = (erc20_balance_of(CHAIN_RPC[chain], usdt_c, address) / (10 ** erc20_decimals(CHAIN_RPC[chain], usdt_c))) if usdt_c else 0.0
    usdc_amt = (erc20_balance_of(CHAIN_RPC[chain], usdc_c, address) / (10 ** erc20_decimals(CHAIN_RPC[chain], usdc_c))) if usdc_c else 0.0
    total_usd = native_usd + usdt_amt * 1.0 + usdc_amt * 1.0
    eth_on_bnb_amt = 0.0
    if chain == "bnb":
        eth_token = "0x2170Ed0880ac9A755fd29B2688956BD959F933F8"
        bal = erc20_balance_of(CHAIN_RPC[chain], eth_token, address)
        if bal > 0:
            dec = erc20_decimals(CHAIN_RPC[chain], eth_token) or 18
            eth_on_bnb_amt = bal / (10**dec)
            native_eth_price = get_eth_usd_price_cached()
            total_usd += eth_on_bnb_amt * native_eth_price

    return{
        "chain": chain,
        "native_symbol": NATIVE_SYMBOL.get(chain, "NATIVE"),
        "native_amount": native_amt,
        "usdt_amount": usdt_amt,
        "usdc_amount": usdc_amt,
        "total_usd": total_usd,
        "eth_on_bnb_amount": eth_on_bnb_amt,
    }



def erc20_balance_of(rpc_url: str, token: str, addr: str) -> int:
    data = "0x70a08231" + ("0"*24 + addr.lower()[2:])
    payload = {"jsonrpc":"2.0","method":"eth_call","params":[{"to":token,"data":data},"latest"],"id":1}
    j = requests.post(rpc_url, json=payload, timeout=15).json()
    res = j.get("result")
    if not res or res == "0x":
        return 0
    try:
        return int(res, 16)
    except Exception:
        return 0

def erc20_decimals(rpc_url: str, token: str) -> int:
    res = requests.post(rpc_url, json={"jsonrpc":"2.0","method":"eth_call","params":[{"to":token,"data":"0x313ce567"},"latest"],"id":1}, timeout=15).json().get("result","0x0")
    return int(res, 16) if res != "0x" else 18


if __name__ == "__main__":

    grand_total = 0.0
    for ch in CHAIN_RPC:
        row = summarize_chain(ch, ADDRESS_EVM)
        parts = [

            f"{row['chain']}: {row['native_symbol']}={row['native_amount']}",
            f"USDT={row['usdt_amount']}",
            f"USDC={row['usdc_amount']}",
        ]
        if ch == "bnb" and row.get('eth_on_bnb_amount', 0.0):
            parts.append(f"ETH_on_bnb={row['eth_on_bnb_amount']}")
        parts.append(f"total_usd={row['total_usd']}")
        print(", ".join(parts))
        grand_total += row["total_usd"]

    print("ALL_CHAINS_TOTAL_USD", grand_total)    







