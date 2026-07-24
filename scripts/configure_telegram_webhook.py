"""Register the configured Telegram webhook without printing credentials."""

from app.core.config import get_settings
from app.services.telegram_daily_balance import (
    TelegramBotClient,
    TelegramSendError,
    resolve_telegram_webhook_secret,
)


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    webhook_secret = resolve_telegram_webhook_secret(settings)

    try:
        TelegramBotClient(settings).configure_webhook(
            settings.telegram_webhook_url,
            webhook_secret,
        )
    except TelegramSendError as exc:
        raise SystemExit(f"Telegram webhook registration failed: {exc.code}") from None
    print(f"Telegram webhook configured: {settings.telegram_webhook_url}")


if __name__ == "__main__":
    main()
