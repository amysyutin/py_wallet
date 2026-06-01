from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import CHAIN_RPC
from app.db.models.asset import Asset
from app.db.models.balance_snapshot import BalanceSnapshot
from app.db.models.snapshot import Snapshot
from app.db.models.wallet import Wallet
from app.deps import CurrentUser, SessionDep
from app.schemas.snapshot import BalanceRead, SnapshotCreate, SnapshotRead
from app.services.snapshot import create_snapshot_for_wallet

router = APIRouter(prefix="/snapshot", tags=["snapshot"])


async def _serialize_snapshot(session: SessionDep, snapshot: Snapshot) -> SnapshotRead:
    rows = await session.execute(
        select(Asset.symbol, BalanceSnapshot.amount, BalanceSnapshot.usd_value)
        .join(Asset, Asset.id == BalanceSnapshot.asset_id)
        .where(BalanceSnapshot.snapshot_id == snapshot.id)
        .order_by(BalanceSnapshot.usd_value.desc())
    )
    balances = [
        BalanceRead(symbol=r.symbol, amount=r.amount, usd_value=r.usd_value)
        for r in rows
    ]
    return SnapshotRead(
        id=snapshot.id,
        wallet_id=snapshot.wallet_id,
        snapshot_at=snapshot.snapshot_at,
        total_usd=snapshot.total_usd,
        balances=balances,
    )


@router.post("", response_model=list[SnapshotRead], status_code=status.HTTP_201_CREATED)
async def take_snapshot(
    payload: SnapshotCreate,
    current_user: CurrentUser,
    session: SessionDep,
) -> list[SnapshotRead]:
    if payload.wallet_id is not None:
        wallet = await session.scalar(
            select(Wallet).where(
                Wallet.id == payload.wallet_id,
                Wallet.user_id == current_user.id,
            )
        )
        if wallet is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
        if wallet.chain_type not in CHAIN_RPC:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Snapshot for chain '{wallet.chain_type}' is not supported yet",
            )
        wallets = [wallet]
    else:
        result = await session.scalars(
            select(Wallet).where(Wallet.user_id == current_user.id)
        )
        wallets = [w for w in result if w.chain_type in CHAIN_RPC]

    if not wallets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No wallets to snapshot")

    out: list[SnapshotRead] = []
    for wallet in wallets:
        snap = await create_snapshot_for_wallet(session, wallet)
        out.append(await _serialize_snapshot(session, snap))
    return out