import os
from dotenv import load_dotenv
load_dotenv()


ADDRESS_EVM = os.getenv("ADDRESS", "")
if ADDRESS_EVM is None:
    raise ValueError("Переменная ADDRESS не найдена в .env или окружении")


# ADDRESS_EVM = {'address': ADDRESS}


RPC_URL_MAIN = os.getenv("RPC_URL_MAINET", "")
RPC_URL_BASE = os.getenv("RPC_URL_BASE", "")
RPC_URL_BNB = os.getenv("RPC_URL_BNB", "")
RPC_URL_ARB = os.getenv("RPC_URL_ARB", "")
RPC_URL_LINEA = os.getenv("RPC_URL_LINEA", "") 

CHAIN_RPC = {
    "mainnet": RPC_URL_MAIN,
    "base": RPC_URL_BASE,
    "bnb": RPC_URL_BNB,
    "arbitrum": RPC_URL_ARB,
    "linea": RPC_URL_LINEA
}


COINGECKO_PLATFORM = {
    "mainnet": "ethereum",
    "base": "base",
    "bnb": "binance-smart-chain",
    "arbitrum": "arbitrum-one",
    "linea": "linea",
}

NATIVE_CG_ID = {
    "mainnet": "ethereum",
    "base": "ethereum",
    "arbitrum": "ethereum",
    "linea": "ethereum",
    "bnb": "binancecoin",
}
NATIVE_SYMBOL = {
    "mainnet": "ETH",
    "base": "ETH",
    "arbitrum": "ETH",
    "linea": "ETH",
    "bnb": "BNB",
}

# Специальная метка для нативного токена
NATIVE_ETH_ADDRESS = "0x0000000000000000000000000000000000000000"

TOKENS_BY_CHAIN = {
    "mainnet": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    },
    "base": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xA7D84C8fFc3C662F95e1b7b78c09D5DDF71F0991",
        "USDC": "0xD9AAe2009bC5542E4A0eA4c2d6bE090E674b1b19",  # Native USDC on Base
    },
    "bnb": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0x55d398326f99059fF775485246999027B3197955",  # Binance-Peg USDT
        "USDC": "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d",  # Binance-Peg USDC
    },
    "arbitrum": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Native USDC
    },
    "linea": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xa219439258ca9da29e9cc4ce5596924745e12b93",
        "USDC": "0xc226f6Df6c60f5a992cEa8a620c10D50fE2F04e4",
    }
}







