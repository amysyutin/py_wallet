from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app.core.normalization import normalize_email
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password_and_update,
)
from app.db.models.user import User, UserRole
from app.deps import CurrentUser, SessionDep
from app.schemas.auth import Token, UserLogin, UserRead, UserRegister

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(payload: UserRegister, session: SessionDep) -> User:
    email = normalize_email(str(payload.email))
    existing = await session.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=email,
        auth_hash=await run_in_threadpool(hash_password, payload.password),
        role=UserRole.user,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, session: SessionDep) -> Token:
    email = normalize_email(str(payload.email))
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    valid, replacement_hash = await run_in_threadpool(
        verify_password_and_update, payload.password, user.auth_hash
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if replacement_hash is not None:
        user.auth_hash = replacement_hash
        await session.commit()
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return current_user
