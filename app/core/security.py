from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_PASSWORD_HASHER = PasswordHasher()


def _legacy_bcrypt_bytes(password: str) -> bytes:
    """Match the historical bcrypt behavior for existing password hashes."""
    return password.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return _PASSWORD_HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    valid, _ = verify_password_and_update(password, password_hash)
    return valid


def verify_password_and_update(
    password: str, password_hash: str
) -> tuple[bool, str | None]:
    """Verify a password and return a replacement hash when migration is needed."""
    if password_hash.startswith("$argon2"):
        try:
            valid = _PASSWORD_HASHER.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False, None
        replacement = (
            _PASSWORD_HASHER.hash(password)
            if _PASSWORD_HASHER.check_needs_rehash(password_hash)
            else None
        )
        return valid, replacement

    if password_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            valid = bcrypt.checkpw(
                _legacy_bcrypt_bytes(password), password_hash.encode("utf-8")
            )
        except ValueError:
            return False, None
        return (True, hash_password(password)) if valid else (False, None)

    return False, None


def create_access_token(subject: str | int) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_ttl_min
    )
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
    except jwt.InvalidTokenError:
        return None
    return payload.get("sub")
