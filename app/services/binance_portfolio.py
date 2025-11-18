from ast import alias
from app.connectors.exchange.binance import (
    get_account_balances_earn_locked,
    get_account_balances_spot,
    sync_server_time,
    get_account_balances_earn,
    filter_nonzero, )
from app.connectors.exchange.binance_public import load_all_price_cached, to_usdt


def summarize_binance_usdt() -> dict:
    sync_server_time()
    try:
        #сюда как то добавить get_account_balances_earn 
        spot_bals = filter_nonzero(get_account_balances_spot())

        earn_bals = get_account_balances_earn()

        loked_bals = get_account_balances_earn_locked()

        print("EARN BALANCES RAW", earn_bals)


    except TimeoutError as e:
        return {"error": str(e), "assets": [], "total_usdt": 0.0}

    prices = load_all_price_cached()

    rows, total_usdt = [], 0.0

    important_assets = {"BTC", "ETH", "BNB", "USDT", "USDC"}


    def process_group(bals: list[dict], source: str):
        nonlocal rows, total_usdt
        for b in bals: 
            asset = b["asset"].upper()
            amount = float(b["amount"])

            alias = {
                "LDUSDT": "USDT",
                "LDETH": "ETH",
                "LDBNB": "BNB",
                "LDBTC": "BTC",
                "LDUSDC": "USDC",
            
            }
            original_asset = asset
            asset = alias.get(asset, asset)

            if asset not in important_assets:
                continue
                
            usd = to_usdt(asset, amount, prices)
            if usd == 0:
                continue

            amount_str = f"{amount:.8f}".rstrip("0").rstrip(".")
            if usd < 0.01:
                usdt_str = "<0.01"
            else:    
                usdt_str = f"{usd:.2f}"

            rows.append(
                {
                    "asset": asset,
                    "amount": amount,
                    "amount_str": amount_str,
                    "usd": usd,
                    "usdt_str": usdt_str,
                    "source": source, 
                }
            )
            total_usdt += usd


    process_group(spot_bals, "spot")
    process_group(earn_bals, "earn_flexible")
    process_group(loked_bals, "earn_loked")

    return {"assets": rows, "total_usdt": total_usdt}       


