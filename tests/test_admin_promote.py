import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.normalization import normalize_email
from app.core.security import hash_password
from app.db.models.user import User, UserRole
from app.services.admin_promote import (
    PromoteAdminStatus,
    promote_admin_by_email,
)


@pytest.mark.asyncio
async def test_promote_admin_not_found(db_session: AsyncSession):
    result = await promote_admin_by_email(db_session, "missing@example.com")
    assert result.status == PromoteAdminStatus.not_found
    assert result.email == "missing@example.com"
    assert result.user_id is None


@pytest.mark.asyncio
async def test_promote_admin_success(db_session: AsyncSession):
    user = User(
        email="promote@example.com",
        auth_hash=hash_password("password12"),
        role=UserRole.user,
    )
    db_session.add(user)
    await db_session.flush()

    result = await promote_admin_by_email(db_session, "  Promote@Example.COM  ")
    assert result.status == PromoteAdminStatus.promoted
    assert result.email == normalize_email("promote@example.com")
    assert result.user_id == user.id
    await db_session.refresh(user)
    assert user.role == UserRole.admin


@pytest.mark.asyncio
async def test_promote_admin_already_admin(db_session: AsyncSession):
    user = User(
        email="already@example.com",
        auth_hash=hash_password("password12"),
        role=UserRole.admin,
    )
    db_session.add(user)
    await db_session.flush()

    result = await promote_admin_by_email(db_session, "already@example.com")
    assert result.status == PromoteAdminStatus.already_admin
    assert result.user_id == user.id
