import requests


def get_balance(rpc_url: str, address: str) -> int:
    payload = {"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1}
    r = requests.post(rpc_url, json=payload, timeout=15)
    r.raise_for_status()
    return int(r.json().get("result","0x0"), 16)


def eth_call(rpc_url: str, to : str, data: str) -> str:
    payload = {"jsonrpc":"2.0","method":"eth_call","params":[{"to":to,"data":data},"latest"],"id":1}
    r = requests.post(rpc_url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json().get("result", "0x")

    





# def erc20_balance_of(rpc_url: str, token: str, addr: str) -> int:
#     data = "0x70a08231" + ("0"*24 + addr.lower()[2:])
#     payload = {"jsonrpc":"2.0","method":"eth_call","params":[{"to":token,"data":data},"latest"],"id":1}
#     j = requests.post(rpc_url, json=payload, timeout=15).json()
#     res = j.get("result")
#     if not res or res == "0x":
#         return 0
#     try:
#         return int(res, 16)
#     except Exception:
#         return 0

# def get_native_eth_balance(chain: str, address: str) -> tuple[int, float]:
#     from app.config import CHAIN_RPC
#     url = CHAIN_RPC.get(chain, "")
#     if not url or not address:
#         return (0, 0.0)
#     payload = {"jsonrpc":"2.0","method":"eth_getBalance","params":[address,"latest"],"id":1} 
#     r = requests.post(url, json=payload, timeout=15)
#     r.raise_for_status()
#     data = r.json()
#     wei = int(data.get("result","0x0"), 16)
#     return wei, wei / 10**18 