import asyncio

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.telegram_daily_balance import send_due_daily_balances


async def _run() -> int:
    settings = get_settings()
    async with SessionLocal() as session:
        sent, failed = await send_due_daily_balances(session, settings)
    print(f"telegram daily balance: sent={sent} failed={failed}")
    return 1 if failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
