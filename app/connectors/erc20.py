from app.connectors.rpc import eth_call

def _pad_addr_32(addr: str) -> str:
    return "0x" + "0"*24 + addr.lower()[2:]


def balance_of(rpc_url: str, token: str, address: str) -> int:
    data = "0x70a08231" + _pad_addr_32(address)[2:]
    res = eth_call(rpc_url, token, data)
    return int(res, 16) if res not in (None, "0x") else 0


_DECIMALS_CACHE: dict[tuple[str,str], int] = {}

def decimals(rpc_url: str, token: str) -> int:
    key = (rpc_url, token.lower())
    if key in _DECIMALS_CACHE:
        return _DECIMALS_CACHE[key]
    res = eth_call(rpc_url, token, "0x313ce567")
    # _DECIMALS_CACHE[key] = int(res, 16) if res is not (None, "0x") else 18
    if not res or res == "0x":
        _DECIMALS_CACHE[key] = 18
    else:
        try:
            _DECIMALS_CACHE[key] = int(res, 16)
        except Exception:
            _DECIMALS_CACHE[key] = 18        
    return _DECIMALS_CACHE[key]







# def erc20_decimals(rpc_url: str, token: str) -> int:
#     res = requests.post(rpc_url, json={"jsonrpc":"2.0","method":"eth_call","params":[{"to":token,"data":"0x313ce567"},"latest"],"id":1}, timeout=15).json().get("result","0x0")
#     return int(res, 16) if res != "0x" else 18