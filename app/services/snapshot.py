from dataclasses import dataclass
from decimal import Decimal

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CHAIN_RPC, NATIVE_ETH_ADDRESS, TOKENS_BY_CHAIN
from app.connectors.price.coingecko import get_native_price_usd_cached
from app.db.models.asset import Asset
from app.db.models.balance_snapshot import BalanceSnapshot
from app.db.models.snapshot import Snapshot
from app.db.models.wallet import Wallet
from app.services.portfolio import summarize_chain


@dataclass
class BalanceItem:
    symbol: str
    chain: str
    contract_address: str
    amount: Decimal
    usd_value: Decimal


def collect_wallet_balances(chain: str, address: str) -> list[BalanceItem]:
    """Синхронный сбор балансов через существующие коннекторы."""
    if not CHAIN_RPC.get(chain):
        return []
    cs = summarize_chain(chain, address)
    items: list[BalanceItem] = []

    if cs.native_amount > 0:
        native_price = get_native_price_usd_cached(chain)
        items.append(
            BalanceItem(
                symbol=cs.native_symbol,
                chain=chain,
                contract_address=NATIVE_ETH_ADDRESS,
                amount=Decimal(str(cs.native_amount)),
                usd_value=Decimal(str(cs.native_amount * native_price)),
            )
        )

    tokens_cfg = TOKENS_BY_CHAIN.get(chain, {})
    if cs.usdt_amount > 0 and tokens_cfg.get("USDT"):
        items.append(
            BalanceItem(
                "USDT",
                chain,
                tokens_cfg["USDT"],
                Decimal(str(cs.usdt_amount)),
                Decimal(str(cs.usdt_amount)),
            )
        )
    if cs.usdc_amount > 0 and tokens_cfg.get("USDC"):
        items.append(
            BalanceItem(
                "USDC",
                chain,
                tokens_cfg["USDC"],
                Decimal(str(cs.usdc_amount)),
                Decimal(str(cs.usdc_amount)),
            )
        )

    for t in cs.tokens:
        if t.amount > 0:
            items.append(
                BalanceItem(
                    t.symbol,
                    chain,
                    f"{chain}:{t.symbol}",
                    Decimal(str(t.amount)),
                    Decimal(str(t.usd)),
                )
            )

    return items


async def _get_or_create_asset(session: AsyncSession, item: BalanceItem) -> Asset:
    asset = await session.scalar(
        select(Asset).where(
            Asset.chain == item.chain,
            Asset.contract_address == item.contract_address,
        )
    )
    if asset is None:
        asset = Asset(
            symbol=item.symbol,
            name=item.symbol,
            contract_address=item.contract_address,
            chain=item.chain,
            decimals=18,
        )
        session.add(asset)
        await session.flush()  # получаем asset.id в рамках транзакции
    return asset


async def create_snapshot_for_wallet(session: AsyncSession, wallet: Wallet) -> Snapshot:
    # блокирующий сбор балансов уводим в threadpool, чтобы не стопорить event loop
    items = await run_in_threadpool(
        collect_wallet_balances, wallet.chain_type, wallet.address
    )

    snapshot = Snapshot(wallet_id=wallet.id, total_usd=Decimal("0"))
    session.add(snapshot)
    await session.flush()  # получаем snapshot.id

    total = Decimal("0")
    for item in items:
        asset = await _get_or_create_asset(session, item)
        session.add(
            BalanceSnapshot(
                snapshot_id=snapshot.id,
                asset_id=asset.id,
                amount=item.amount,
                usd_value=item.usd_value,
            )
        )
        total += item.usd_value

    snapshot.total_usd = total
    await session.commit()
    await session.refresh(snapshot)
    return snapshot
