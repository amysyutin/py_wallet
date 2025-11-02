from typing import List
from app.models import Asset
import os, requests
from app.config import ADDRESS_EVM, RPC_URL_MAIN, RPC_URL_BASE, CHAIN_RPC

print(bool(RPC_URL_BASE), bool(RPC_URL_MAIN), ADDRESS_EVM[:10], list(CHAIN_RPC.keys()))


def get_eth_balance_via_rpc(address: str) -> tuple[int, float]:
    # Получаю баланс eth через rpc-запрос
    url_main = RPC_URL_MAIN
    if not url_main:
        print("RPC_URL пуст")
        return (0, 0.0)    

    if not address:
        print("Пустой address - не передан адрес кошелька")
        return (0, 0.0)

    payload = {
        "jsonrpc":"2.0",
        "method":"eth_getBalance",
        "params":[address,"latest"],
        "id":1
        }

    try:
        r = requests.post(url_main, json=payload, timeout=15)
        r.raise_for_status() #if status 4xx/5xx
        data = r.json()
        if "error" in data or "result" not in data:
            print(f"Ошибка RPC: {data}")
            return (0, 0.0)
        wei = int(data["result"], 16)
        return wei, wei / 10**18
    except Exception as e:
        print(f"Ошибка при запросе RPC: {e}")
        return (0, 0.0)


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

    

def _assets_native_usd(address: str) -> List[Asset]:
    from app.config import CHAIN_RPC
    eth_usd = get_eth_usd_price()
    assets, total = [], 0.0
    for chain in CHAIN_RPC:
        _, eth = get_native_eth_balance(chain, address)
        usd = eth * eth_usd
        total += usd
        assets.append(Asset(name=f"ETH:{chain}", price=usd, source="evm-rpc"))
    assets.append(Asset(name="TOTAL_USD", price=total, source="evm-rpc"))
    return assets    

async def get_evm_balances(address: str) -> List[Asset]:

    if not address:
        from app.config import ADDRESS_EVM
        address = ADDRESS_EVM


    print(_assets_native_usd(address))
    print(address)
    return _assets_native_usd(address)



if __name__ == "__main__":
    addr = ADDRESS_EVM
    wei, eth = get_eth_balance_via_rpc(addr)
    print(f"Баланс {addr[:10]}... = {eth} ETH")






