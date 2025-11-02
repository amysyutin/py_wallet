from fastapi import HTTPException
from fastapi.routing import APIRouter
from app.sources.evm import get_evm_balances
from app.config import ADDRESS_EVM


router = APIRouter()

@router.get("/health")
async def health():
    return {"status": "healthy"}

@router.get("/assets")
async def get_assets(address: str = ""):
    resolved_address = address or ADDRESS_EVM
    if not resolved_address:
        raise HTTPException(status_code=400, detail="ADDRESS не задан и параметр address не передан")
    balances = await get_evm_balances(resolved_address)
    return [b.model_dump() for b in balances]
