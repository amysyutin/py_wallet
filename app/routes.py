from fastapi import HTTPException, status
from sqlalchemy import text

from fastapi.routing import APIRouter
from app.config import ADDRESS_EVM
from app.demo.binance_balance import DEMO_BINANCE_BALANCE
from app.deps import AdminUser
from app.services.portfolio import summarize_all
from app.services.binance_portfolio import summarize_binance_usdt
from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "healthy"}


@router.get("/assets")
async def get_assets(address: str = ""):
    resolved = address or ADDRESS_EVM
    if not resolved:
        raise HTTPException(
            status_code=400,
            detail="EVM1_ADDRESS не задан и параметр address не передан",
        )
    summary = summarize_all(resolved)
    return summary.model_dump()


@router.get("/demo/binance/balance", tags=["demo"])
async def demo_binance_balance():
    return DEMO_BINANCE_BALANCE


@router.get("/binance/balance", tags=["binance"])
async def binance_balance(_admin: AdminUser):
    return summarize_binance_usdt()
