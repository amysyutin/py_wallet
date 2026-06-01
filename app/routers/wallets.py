from fastapi import APIRouter, status
from sqlalchemy import select

from app.db.models.wallet import Wallet
from app.deps import CurrentUser, SessionDep
from app.schemas.wallet import WalletCreate, WalletRead

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.post("", response_model=WalletRead, status_code=status.HTTP_201_CREATED)
async def create_wallet(
    payload: WalletCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> Wallet:
    wallet = Wallet(
        user_id=current_user.id,
        label=payload.label,
        address=payload.address,
        chain_type=payload.chain_type,
    )
    session.add(wallet)
    await session.commit()
    await session.refresh(wallet)
    return wallet


@router.get("", response_model=list[WalletRead])
async def list_wallets(
    current_user: CurrentUser,
    session: SessionDep,
) -> list[Wallet]:
    result = await session.scalars(
        select(Wallet)
        .where(Wallet.user_id == current_user.id)
        .order_by(Wallet.id)
    )
    return list(result)