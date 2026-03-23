from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core import settings


def hash_password(plain: str) -> str:
    b_plain = plain.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hash_plain = bcrypt.hashpw(b_plain, salt)
    return hash_plain.decode()


def verify_password(plain: str, hashed: str) -> bool:
    b_plain = plain.encode("utf-8")
    b_hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(b_plain, b_hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expires_delta = timedelta(
        minutes=settings.security.access_token_expire_minutes
    )
    expire = datetime.now(UTC) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(
        to_encode,
        settings.security.secret_key,
        algorithm=settings.security.algorithm,
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.security.secret_key,
            algorithms=[settings.security.algorithm],
        )
        return payload
    except jwt.PyJWTError:
        raise ValueError("Invalid token") from None
