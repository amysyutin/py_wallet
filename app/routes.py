from fastapi import HTTPException
from fastapi.routing import APIRouter
from app.config import ADDRESS_EVM
from app.services.portfolio import summarize_all
from app.services.binance_portfolio import summarize_binance_usdt


router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "healthy"}

@router.get("/assets")
async def get_assets(address: str = ""):
    resolved = address or ADDRESS_EVM
    if not resolved:
        raise HTTPException(status_code=400, detail="ADDRESS не задан и параметр address не передан")
    summary = summarize_all(resolved)
    return summary.model_dump()


@router.get("/binance/balance")
async def binance_balance():
    return summarize_binance_usdt()


    

