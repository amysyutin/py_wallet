from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from zoneinfo import ZoneInfo

import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.telegram import (
    TelegramAccount,
    TelegramDigestDelivery,
    TelegramNotificationSettings,
)
from app.db.models.wallet import Wallet
from app.services.wallet_view import build_wallet_balance_info

DELIVERY_LEASE_SECONDS = 10 * 60
MAX_DELIVERY_ATTEMPTS = 3
MAX_RETRY_AFTER_SECONDS = 24 * 60 * 60


class TelegramSendError(RuntimeError):
    """A sanitized Telegram delivery failure safe to persist and log."""

    def __init__(
        self,
        code: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


def resolve_telegram_webhook_secret(settings: Settings) -> str:
    if settings.telegram_webhook_secret:
        return settings.telegram_webhook_secret
    if not settings.telegram_bot_token:
        return ""
    return sha256(
        f"pywallet-telegram-webhook-v1:{settings.telegram_bot_token}".encode()
    ).hexdigest()


def format_daily_balance(
    total_usd: Decimal, *, language: str, as_of: datetime | None
) -> str:
    amount = f"${total_usd:,.2f}"
    timestamp = (
        as_of.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if as_of else None
    )
    if language == "ru":
        lines = ["Ваш портфель", "", f"Общая стоимость: {amount}"]
        lines.append(f"Данные на: {timestamp}" if timestamp else "Снимков пока нет")
    else:
        lines = ["Your portfolio", "", f"Total value: {amount}"]
        lines.append(f"As of: {timestamp}" if timestamp else "No snapshots yet")
    return "\n".join(lines)


class TelegramBotClient:
    def __init__(self, settings: Settings):
        self._token = settings.telegram_bot_token
        self._base_url = settings.telegram_api_base_url.rstrip("/")
        self._timeout = settings.telegram_request_timeout_seconds

    def _send_message(
        self, chat_id: int, text: str, mini_app_url: str, button_text: str
    ) -> None:
        try:
            response = requests.post(
                f"{self._base_url}/bot{self._token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {
                                    "text": button_text,
                                    "web_app": {"url": mini_app_url},
                                }
                            ]
                        ]
                    },
                },
                timeout=self._timeout,
            )
        except requests.RequestException:
            # Request URLs contain the bot token; do not retain the original
            # exception as a chained cause that a traceback could expose.
            raise TelegramSendError("telegram_network_error") from None

        try:
            payload = response.json()
        except (requests.JSONDecodeError, ValueError):
            payload = {}
        if response.ok and payload.get("ok"):
            return

        parameters = payload.get("parameters")
        retry_after = (
            parameters.get("retry_after") if isinstance(parameters, dict) else None
        )
        if not isinstance(retry_after, int) or retry_after < 0:
            retry_after = None
        status_code = response.status_code
        raise TelegramSendError(
            f"telegram_http_{status_code}",
            status_code=status_code,
            retry_after_seconds=retry_after,
        )

    def send_daily_balance(
        self, chat_id: int, text: str, mini_app_url: str, button_text: str
    ) -> None:
        self._send_message(chat_id, text, mini_app_url, button_text)

    def configure_webhook(self, webhook_url: str, secret_token: str) -> None:
        try:
            response = requests.post(
                f"{self._base_url}/bot{self._token}/setWebhook",
                json={
                    "url": webhook_url,
                    "secret_token": secret_token,
                    "allowed_updates": ["message"],
                },
                timeout=self._timeout,
            )
        except requests.RequestException:
            raise TelegramSendError("telegram_webhook_network_error") from None

        try:
            payload = response.json()
        except (requests.JSONDecodeError, ValueError):
            payload = {}
        if response.ok and payload.get("ok"):
            return
        raise TelegramSendError(
            f"telegram_webhook_http_{response.status_code}",
            status_code=response.status_code,
        )

    def send_start_message(
        self, chat_id: int, *, language: str, mini_app_url: str
    ) -> None:
        if language == "ru":
            text = (
                "👋 Добро пожаловать в PyWallet!\n\n"
                "Чтобы перейти к своим кошелькам и портфелю, "
                "нажми «Открыть PyWallet»."
            )
            button_text = "Открыть PyWallet"
        else:
            text = (
                "👋 Welcome to PyWallet!\n\n"
                "To view your wallets and portfolio, tap “Open PyWallet”."
            )
            button_text = "Open PyWallet"
        self._send_message(chat_id, text, mini_app_url, button_text)


async def persisted_portfolio_total(
    session: AsyncSession, user_id: int
) -> tuple[Decimal, datetime | None]:
    wallets = list(
        await session.scalars(
            select(Wallet).where(Wallet.user_id == user_id, Wallet.is_active.is_(True))
        )
    )
    if not wallets:
        return Decimal("0"), None
    balance_info = await build_wallet_balance_info(session, wallets)
    total = sum(
        (balance_info[wallet.id].balance_usd for wallet in wallets), Decimal("0")
    )
    snapshot_dates = [
        balance_info[wallet.id].last_snapshot_at
        for wallet in wallets
        if balance_info[wallet.id].last_snapshot_at is not None
    ]
    return total, max(snapshot_dates) if snapshot_dates else None


def _is_due(settings: TelegramNotificationSettings, now: datetime) -> date | None:
    local_now = now.astimezone(ZoneInfo(settings.timezone))
    if local_now.time().replace(tzinfo=None) < settings.daily_at:
        return None
    return local_now.date()


async def send_due_daily_balances(
    session: AsyncSession,
    settings: Settings,
    *,
    now: datetime | None = None,
    client: TelegramBotClient | None = None,
) -> tuple[int, int]:
    """Send due opt-in digests. Returns (sent, failed)."""
    if not settings.telegram_daily_balance_enabled or not settings.telegram_bot_token:
        return 0, 0
    current = now or datetime.now(timezone.utc)
    rows = list(
        await session.execute(
            select(TelegramAccount, TelegramNotificationSettings)
            .join(
                TelegramNotificationSettings,
                TelegramNotificationSettings.telegram_account_id == TelegramAccount.id,
            )
            .where(
                TelegramNotificationSettings.enabled.is_(True),
            )
        )
    )
    bot = client or TelegramBotClient(settings)
    sent = failed = 0
    for account, notification in rows:
        local_date = _is_due(notification, current)
        if local_date is None:
            continue
        delivery = await session.scalar(
            select(TelegramDigestDelivery)
            .where(
                TelegramDigestDelivery.telegram_account_id == account.id,
                TelegramDigestDelivery.local_date == local_date,
            )
            .with_for_update()
        )
        if delivery is not None:
            if delivery.status == "sent":
                continue
            if delivery.retry_after is not None and current < delivery.retry_after:
                continue
            if delivery.attempts >= MAX_DELIVERY_ATTEMPTS:
                continue
            if (
                delivery.status == "pending"
                and delivery.attempted_at is not None
                and current - delivery.attempted_at
                < timedelta(seconds=DELIVERY_LEASE_SECONDS)
            ):
                continue
        total, as_of = await persisted_portfolio_total(session, account.user_id)
        if delivery is None:
            delivery_id = await session.scalar(
                insert(TelegramDigestDelivery)
                .values(
                    telegram_account_id=account.id,
                    local_date=local_date,
                    status="pending",
                    total_usd=str(total),
                    attempts=1,
                    attempted_at=current,
                )
                .on_conflict_do_nothing(constraint="uq_telegram_digest_local_date")
                .returning(TelegramDigestDelivery.id)
            )
            if delivery_id is None:
                await session.rollback()
                continue
            delivery = await session.get(TelegramDigestDelivery, delivery_id)
            if delivery is None:
                await session.rollback()
                continue
        else:
            delivery.status = "pending"
            delivery.total_usd = str(total)
            delivery.error = None
            delivery.attempts += 1
            delivery.attempted_at = current
            delivery.retry_after = None
        await session.commit()
        text = format_daily_balance(total, language=notification.language, as_of=as_of)
        try:
            bot.send_daily_balance(
                account.telegram_user_id,
                text,
                settings.telegram_mini_app_url,
                (
                    "Открыть портфель"
                    if notification.language == "ru"
                    else "Open portfolio"
                ),
            )
        except TelegramSendError as exc:
            delivery.status = "failed"
            delivery.error = exc.code
            if exc.retry_after_seconds is not None:
                delivery.retry_after = current + timedelta(
                    seconds=min(exc.retry_after_seconds, MAX_RETRY_AFTER_SECONDS)
                )
            if exc.status_code == 403:
                notification.enabled = False
            failed += 1
        except Exception:
            delivery.status = "failed"
            delivery.error = "telegram_unexpected_error"
            failed += 1
        else:
            delivery.status = "sent"
            delivery.sent_at = datetime.now(timezone.utc)
            sent += 1
        await session.commit()
    return sent, failed
