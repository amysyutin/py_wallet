from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.asset import Asset


async def get_or_create_manual_asset(
    session: AsyncSession,
    *,
    symbol: str,
    chain: str = "manual",
) -> Asset:
    normalized_symbol = symbol.strip().upper()
    normalized_chain = chain.strip().lower() or "manual"

    asset = await session.scalar(
        select(Asset).where(
            Asset.chain == normalized_chain,
            Asset.symbol == normalized_symbol,
            Asset.contract_address.is_(None),
        )
    )
    if asset is None:
        asset = Asset(
            symbol=normalized_symbol,
            name=normalized_symbol,
            contract_address=None,
            chain=normalized_chain,
            decimals=18,
        )
        session.add(asset)
        await session.flush()
    return asset
