import sys

from app.db.session import SessionLocal
from app.services.admin_promote import PromoteAdminStatus, promote_admin_by_email


async def run_promote_admin_cli(email: str) -> int:
    async with SessionLocal() as session:
        result = await promote_admin_by_email(session, email)
        if result.status == PromoteAdminStatus.promoted:
            await session.commit()
            print(f"promoted {result.email} (user_id={result.user_id})")
            return 0
        await session.rollback()
        if result.status == PromoteAdminStatus.not_found:
            print(f"user not found: {result.email}", file=sys.stderr)
            return 1
        print(f"already admin: {result.email} (user_id={result.user_id})")
        return 2
