"""Unit-тесты коннекторов: rpc, erc20, coingecko — с моком HTTP-запросов."""

from unittest.mock import patch, MagicMock

from app.connectors.rpc import get_balance, eth_call
from app.connectors.erc20 import balance_of, decimals, _DECIMALS_CACHE


# ─── RPC: get_balance ───────────────────────────────────────────────────────


@patch("app.connectors.rpc.requests.post")
def test_get_balance_parses_hex(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "0xde0b6b3a7640000"}
    mock_post.return_value = mock_resp

    result = get_balance("https://rpc.example.com", "0xABC")
    assert result == 10**18


@patch("app.connectors.rpc.requests.post")
def test_get_balance_zero(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "0x0"}
    mock_post.return_value = mock_resp

    assert get_balance("https://rpc.example.com", "0xABC") == 0


@patch("app.connectors.rpc.requests.post")
def test_get_balance_sends_correct_method(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "0x0"}
    mock_post.return_value = mock_resp

    get_balance("https://rpc.example.com", "0xDEAD")
    call_kwargs = mock_post.call_args
    payload = call_kwargs[1]["json"]
    assert payload["method"] == "eth_getBalance"
    assert payload["params"][0] == "0xDEAD"


# ─── RPC: eth_call ──────────────────────────────────────────────────────────


@patch("app.connectors.rpc.requests.post")
def test_eth_call_returns_result(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "0x00000000000000000000000000000000000000000000000000000000000f4240"}
    mock_post.return_value = mock_resp

    result = eth_call("https://rpc.example.com", "0xToken", "0x70a08231abc")
    assert result == "0x00000000000000000000000000000000000000000000000000000000000f4240"


@patch("app.connectors.rpc.requests.post")
def test_eth_call_fallback_on_missing_result(mock_post):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    mock_post.return_value = mock_resp

    result = eth_call("https://rpc.example.com", "0xToken", "0xdata")
    assert result == "0x"


# ─── ERC20: balance_of ──────────────────────────────────────────────────────


@patch("app.connectors.erc20.eth_call")
def test_balance_of_parses_hex(mock_eth_call):
    mock_eth_call.return_value = "0x00000000000000000000000000000000000000000000000000000000000f4240"
    result = balance_of("https://rpc", "0xToken", "0xAddress")
    assert result == 1_000_000


@patch("app.connectors.erc20.eth_call")
def test_balance_of_zero_result(mock_eth_call):
    mock_eth_call.return_value = "0x"
    assert balance_of("https://rpc", "0xToken", "0xAddr") == 0


@patch("app.connectors.erc20.eth_call")
def test_balance_of_none_result(mock_eth_call):
    mock_eth_call.return_value = None
    assert balance_of("https://rpc", "0xToken", "0xAddr") == 0


# ─── ERC20: decimals ────────────────────────────────────────────────────────


@patch("app.connectors.erc20.eth_call")
def test_decimals_parses_6(mock_eth_call):
    _DECIMALS_CACHE.clear()
    mock_eth_call.return_value = "0x0000000000000000000000000000000000000000000000000000000000000006"
    result = decimals("https://rpc-test", "0xtokenA")
    assert result == 6


@patch("app.connectors.erc20.eth_call")
def test_decimals_default_18_on_empty(mock_eth_call):
    _DECIMALS_CACHE.clear()
    mock_eth_call.return_value = "0x"
    result = decimals("https://rpc-test", "0xtokenB")
    assert result == 18


@patch("app.connectors.erc20.eth_call")
def test_decimals_cached(mock_eth_call):
    _DECIMALS_CACHE.clear()
    mock_eth_call.return_value = "0x0000000000000000000000000000000000000000000000000000000000000012"
    decimals("https://rpc-cache", "0xtokenC")
    decimals("https://rpc-cache", "0xtokenC")
    assert mock_eth_call.call_count == 1


# ─── CoinGecko ──────────────────────────────────────────────────────────────


@patch("app.connectors.price.coingecko.requests.get")
def test_get_eth_usd_price_cached(mock_get):
    import app.connectors.price.coingecko as cg
    cg.ETH_USD_CACHE = None

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"ethereum": {"usd": 3500.0}}
    mock_get.return_value = mock_resp

    price = cg.get_eth_usd_price_cached()
    assert price == 3500.0

    price2 = cg.get_eth_usd_price_cached()
    assert price2 == 3500.0
    assert mock_get.call_count == 1

    cg.ETH_USD_CACHE = None


@patch("app.connectors.price.coingecko.requests.get")
def test_get_native_price_unknown_chain(mock_get):
    import app.connectors.price.coingecko as cg
    price = cg.get_native_price_usd_cached("unknown_chain")
    assert price == 0.0
    mock_get.assert_not_called()


@patch("app.connectors.price.coingecko.requests.get")
def test_get_native_price_bnb(mock_get):
    import app.connectors.price.coingecko as cg
    cg.NATIVE_PRICE_CACHE.pop("binancecoin", None)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"binancecoin": {"usd": 420.0}}
    mock_get.return_value = mock_resp

    price = cg.get_native_price_usd_cached("bnb")
    assert price == 420.0

    cg.NATIVE_PRICE_CACHE.pop("binancecoin", None)


@patch("app.connectors.price.coingecko.requests.get")
def test_get_native_price_handles_exception(mock_get):
    import app.connectors.price.coingecko as cg
    cg.NATIVE_PRICE_CACHE.pop("binancecoin", None)

    mock_get.side_effect = Exception("Network error")
    price = cg.get_native_price_usd_cached("bnb")
    assert price == 0.0

    cg.NATIVE_PRICE_CACHE.pop("binancecoin", None)
