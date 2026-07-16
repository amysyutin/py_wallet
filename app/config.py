import os
from dotenv import load_dotenv

load_dotenv()

ADDRESS_EVM = os.getenv("EVM1_ADDRESS") or ""

RPC_URL_MAIN = os.getenv("RPC_URL_MAINNET", "")
RPC_URL_BASE = os.getenv("RPC_URL_BASE", "")
RPC_URL_BNB = os.getenv("RPC_URL_BNB", "")
RPC_URL_ARB = os.getenv("RPC_URL_ARB", "")
RPC_URL_LINEA = os.getenv("RPC_URL_LINEA", "")

CHAIN_RPC = {
    "mainnet": RPC_URL_MAIN,
    "base": RPC_URL_BASE,
    "bnb": RPC_URL_BNB,
    "arbitrum": RPC_URL_ARB,
    "linea": RPC_URL_LINEA,
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
        "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # Native USDC
        "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
    },
    "bnb": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0x55d398326f99059fF775485246999027B3197955",  # Binance-Peg USDT
        "BINANCE_PEG_USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
    },
    "arbitrum": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9",
        "USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Native USDC
        "USDC.e": "0xFF970A61A04b1cA14834A43f5de4533eBDDB5CC8",
    },
    "linea": {
        "ETH": NATIVE_ETH_ADDRESS,
        "USDT": "0xa219439258ca9da29e9cc4ce5596924745e12b93",
        "USDC": "0x176211869cA2b568f2A7D4EE941E073a821EE1ff",  # Native USDC
    },
}
