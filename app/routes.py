from fastapi import HTTPException, status
from sqlalchemy import text

from fastapi.routing import APIRouter
from app.config import ADDRESS_EVM
from app.services.portfolio import summarize_all
from app.db.session import engine

router = APIRouter()


async def _assert_database_available() -> None:
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@router.get("/health/live")
async def health_live():
    return {"status": "alive"}


@router.get("/health/ready")
async def health_ready():
    try:
        await _assert_database_available()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        )
    return {"status": "ready"}


@router.get("/health")
async def health():
    try:
        await _assert_database_available()
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
