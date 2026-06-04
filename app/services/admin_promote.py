from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User, UserRole


class PromoteAdminStatus(str, Enum):
    promoted = "promoted"
    not_found = "not_found"
    already_admin = "already_admin"


@dataclass(frozen=True)
class PromoteAdminResult:
    status: PromoteAdminStatus
    email: str
    user_id: int | None = None


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def promote_admin_by_email(
    session: AsyncSession,
    email: str,
) -> PromoteAdminResult:
    normalized = normalize_email(email)
    user = await session.scalar(select(User).where(User.email == normalized))
    if user is None:
        return PromoteAdminResult(
            status=PromoteAdminStatus.not_found,
            email=normalized,
        )
    if user.role == UserRole.admin:
        return PromoteAdminResult(
            status=PromoteAdminStatus.already_admin,
            email=normalized,
            user_id=user.id,
        )
    user.role = UserRole.admin
    await session.flush()
    return PromoteAdminResult(
        status=PromoteAdminStatus.promoted,
        email=normalized,
        user_id=user.id,
    )
