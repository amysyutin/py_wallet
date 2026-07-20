"""Register the configured Telegram webhook without printing credentials."""

from __future__ import annotations

import requests

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    if not settings.telegram_webhook_secret:
        raise SystemExit("TELEGRAM_WEBHOOK_SECRET is required")

    try:
        response = requests.post(
            f"{settings.telegram_api_base_url.rstrip('/')}/bot{settings.telegram_bot_token}/setWebhook",
            json={
                "url": settings.telegram_webhook_url,
                "secret_token": settings.telegram_webhook_secret,
                "allowed_updates": ["message"],
            },
            timeout=settings.telegram_request_timeout_seconds,
        )
    except requests.RequestException:
        raise SystemExit(
            "Telegram webhook registration failed: network error"
        ) from None

    try:
        payload = response.json()
    except (requests.JSONDecodeError, ValueError):
        payload = {}
    if not response.ok or not payload.get("ok"):
        raise SystemExit(
            f"Telegram webhook registration failed: HTTP {response.status_code}"
        )
    print(f"Telegram webhook configured: {settings.telegram_webhook_url}")


if __name__ == "__main__":
    main()
