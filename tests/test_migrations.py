from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def test_snapshot_read_model_tables_are_migrated(db_session: AsyncSession):
    for table_name in (
        "snapshot_runs",
        "wallet_snapshots",
        "chain_snapshots",
        "snapshot_balance_snapshots",
    ):
        relation = await db_session.scalar(
            text("SELECT to_regclass(:table_name)"),
            {"table_name": f"public.{table_name}"},
        )
        assert relation == table_name
