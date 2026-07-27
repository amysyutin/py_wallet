from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.normalization import normalize_email
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    verify_password_and_update,
)
from app.db.models.user import User, UserRole
from app.db.models.telegram import TelegramAccount, TelegramNotificationSettings
from app.core.config import get_settings
from app.deps import ClientChannel, CurrentUser, SessionDep
from app.metrics import REGISTRATION_COMPLETED
from app.schemas.auth import (
    PasswordChangeRequest,
    TelegramAuthRequest,
    TelegramAuthResponse,
    TelegramLinkEmailRequest,
    Token,
    UserLogin,
    UserRead,
    UserRegister,
)
from app.services.telegram_auth import TelegramInitDataError, validate_init_data

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserRegister,
    session: SessionDep,
    client_channel: ClientChannel,
) -> User:
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
    REGISTRATION_COMPLETED.labels(channel=client_channel).inc()
    return user


@router.post("/login", response_model=Token)
async def login(payload: UserLogin, session: SessionDep) -> Token:
    email = normalize_email(str(payload.email))
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    if user.auth_hash is None:
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


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> None:
    if current_user.auth_hash is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Password login is not configured for this account",
        )
    valid = await run_in_threadpool(
        verify_password, payload.current_password, current_user.auth_hash
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    current_user.auth_hash = await run_in_threadpool(
        hash_password, payload.new_password
    )
    await session.commit()


@router.post("/telegram", response_model=TelegramAuthResponse)
async def telegram_login(
    payload: TelegramAuthRequest, session: SessionDep
) -> TelegramAuthResponse:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Telegram authentication is not configured",
        )
    try:
        telegram_user = validate_init_data(
            payload.init_data,
            settings.telegram_bot_token,
            max_age_seconds=settings.telegram_auth_max_age_seconds,
        )
    except TelegramInitDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    account = await session.scalar(
        select(TelegramAccount).where(
            TelegramAccount.telegram_user_id == telegram_user.id
        )
    )
    is_new_user = account is None
    if account is None:
        user = User(email=None, auth_hash=None, role=UserRole.user)
        session.add(user)
        await session.flush()
        account = TelegramAccount(
            user_id=user.id,
            telegram_user_id=telegram_user.id,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            username=telegram_user.username,
            language_code=telegram_user.language_code,
            allows_write_to_pm=telegram_user.allows_write_to_pm,
        )
        session.add(account)
        await session.flush()
        language = (
            "ru" if (telegram_user.language_code or "").startswith("ru") else "en"
        )
        session.add(
            TelegramNotificationSettings(
                telegram_account_id=account.id,
                enabled=False,
                timezone="UTC",
                language=language,
            )
        )
    else:
        user = await session.get(User, account.user_id)
        if user is None:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "Telegram account is invalid"
            )
        account.first_name = telegram_user.first_name
        account.last_name = telegram_user.last_name
        account.username = telegram_user.username
        account.language_code = telegram_user.language_code
        account.allows_write_to_pm = (
            account.allows_write_to_pm or telegram_user.allows_write_to_pm
        )
        account.last_authenticated_at = datetime.now(timezone.utc)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Telegram account already exists"
        ) from exc
    if is_new_user:
        # The authenticated endpoint itself is the channel source of truth.
        REGISTRATION_COMPLETED.labels(channel="telegram").inc()
    return TelegramAuthResponse(
        access_token=create_access_token(user.id),
        is_new_user=is_new_user,
        email_linked=user.email is not None,
    )


@router.post("/telegram/link-email", response_model=Token)
async def telegram_link_email(
    payload: TelegramLinkEmailRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> Token:
    account = await session.scalar(
        select(TelegramAccount).where(TelegramAccount.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Telegram login required")
    email = normalize_email(str(payload.email))
    target = await session.scalar(select(User).where(User.email == email))
    if target is None or target.auth_hash is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    valid, replacement_hash = await run_in_threadpool(
        verify_password_and_update, payload.password, target.auth_hash
    )
    if not valid:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    if target.id == current_user.id:
        return Token(access_token=create_access_token(target.id))
    target_telegram = await session.scalar(
        select(TelegramAccount).where(TelegramAccount.user_id == target.id)
    )
    if target_telegram is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email account is already linked")
    # Telegram-only users can only be merged before they acquire portfolio data.
    from app.db.models.wallet import Wallet
    from app.db.models.wallet_group import WalletGroup

    wallet_count = await session.scalar(
        select(func.count())
        .select_from(Wallet)
        .where(Wallet.user_id == current_user.id)
    )
    if wallet_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Telegram account has portfolio data and cannot be merged automatically",
        )
    group_count = await session.scalar(
        select(func.count())
        .select_from(WalletGroup)
        .where(WalletGroup.user_id == current_user.id)
    )
    if group_count:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Telegram account has portfolio data and cannot be merged automatically",
        )
    account.user_id = target.id
    if replacement_hash is not None:
        target.auth_hash = replacement_hash
    await session.flush()
    await session.delete(current_user)
    await session.commit()
    return Token(access_token=create_access_token(target.id))
