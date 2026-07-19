from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qsl


class TelegramInitDataError(ValueError):
    pass


@dataclass(frozen=True)
class TelegramUserData:
    id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    allows_write_to_pm: bool


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int,
    now: datetime | None = None,
) -> TelegramUserData:
    """Validate Telegram Mini App initData according to the Bot API contract."""
    if not bot_token:
        raise TelegramInitDataError("Telegram authentication is not configured")
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise TelegramInitDataError("Malformed Telegram init data") from exc
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise TelegramInitDataError("Duplicate Telegram init data field")
    values = dict(pairs)
    received_hash = values.pop("hash", None)
    if not received_hash or len(received_hash) != 64:
        raise TelegramInitDataError("Missing or invalid Telegram hash")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramInitDataError("Invalid Telegram signature")

    try:
        auth_date = datetime.fromtimestamp(int(values["auth_date"]), timezone.utc)
        raw_user = json.loads(values["user"])
        user_id = int(raw_user["id"])
        first_name = str(raw_user["first_name"]).strip()
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        OverflowError,
    ) as exc:
        raise TelegramInitDataError("Invalid Telegram user data") from exc
    current = now or datetime.now(timezone.utc)
    age = (current - auth_date).total_seconds()
    if age < -30 or age > max_age_seconds:
        raise TelegramInitDataError("Expired Telegram init data")
    if user_id <= 0 or not first_name:
        raise TelegramInitDataError("Invalid Telegram user data")

    def optional_string(name: str, max_length: int) -> str | None:
        value = raw_user.get(name)
        if value is None:
            return None
        return str(value).strip()[:max_length] or None

    return TelegramUserData(
        id=user_id,
        first_name=first_name[:128],
        last_name=optional_string("last_name", 128),
        username=optional_string("username", 64),
        language_code=optional_string("language_code", 16),
        allows_write_to_pm=values.get("allows_write_to_pm") == "true",
    )
