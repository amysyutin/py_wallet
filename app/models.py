from pydantic import BaseModel

class Asset(BaseModel):
    name: str
    price: float
    source: str

class TokenBalance(BaseModel):
    symbol: str
    amount: float
    usd: float

class ChainSummary(BaseModel):
    chain: str
    native_symbol: str
    native_amount: float
    usdt_amount: float
    usdc_amount: float
    tokens: list[TokenBalance] = []

class PortfolioSummary(BaseModel):
    address: str
    chains: list[ChainSummary]
    total_usd: float