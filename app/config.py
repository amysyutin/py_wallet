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






