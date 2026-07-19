from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.db.models.telegram import TelegramAccount, TelegramNotificationSettings
from app.deps import CurrentUser, SessionDep
from app.schemas.telegram import TelegramSettingsRead, TelegramSettingsUpdate

router = APIRouter(prefix="/telegram", tags=["telegram"])


async def _account_and_settings(current_user: CurrentUser, session: SessionDep):
    account = await session.scalar(
        select(TelegramAccount).where(TelegramAccount.user_id == current_user.id)
    )
    if account is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram account is not linked")
    settings = await session.get(TelegramNotificationSettings, account.id)
    if settings is None:
        settings = TelegramNotificationSettings(telegram_account_id=account.id)
        session.add(settings)
        await session.flush()
    return account, settings


def _response(account, settings) -> TelegramSettingsRead:
    return TelegramSettingsRead(
        enabled=settings.enabled,
        timezone=settings.timezone,
        daily_at=settings.daily_at,
        language=settings.language,
        allows_write_to_pm=account.allows_write_to_pm,
    )


@router.get("/settings", response_model=TelegramSettingsRead)
async def get_telegram_settings(
    current_user: CurrentUser, session: SessionDep
) -> TelegramSettingsRead:
    account, settings = await _account_and_settings(current_user, session)
    return _response(account, settings)


@router.patch("/settings", response_model=TelegramSettingsRead)
async def update_telegram_settings(
    payload: TelegramSettingsUpdate,
    current_user: CurrentUser,
    session: SessionDep,
) -> TelegramSettingsRead:
    account, settings = await _account_and_settings(current_user, session)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(settings, key, value)
    await session.commit()
    return _response(account, settings)
