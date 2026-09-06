import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import bcrypt
import jwt
import structlog
from anyio import to_thread

from app.core import settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError

logger = structlog.get_logger(__name__)


def hash_password(plain: str) -> str:
    b_plain = plain.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hash_plain = bcrypt.hashpw(b_plain, salt)
    return hash_plain.decode()


def verify_password(plain: str, hashed: str) -> bool:
    b_plain = plain.encode("utf-8")
    b_hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(b_plain, b_hashed)


@lru_cache(maxsize=1)
def _dummy_hash() -> bytes:
    """A hash of a value nobody can present, built once on first use.

    Derived through ``hash_password`` on purpose, so it tracks the cost
    parameter automatically if the rounds ever change.
    """
    return hash_password(secrets.token_urlsafe(32)).encode("utf-8")


def burn_password_time() -> None:
    """Spend the same bcrypt time as ``verify_password``, discard the result.

    Call this on the "no such user" branch of a login. Without it the two
    failures are trivially distinguishable by response time - a lookup miss
    returns in single-digit ms while a real verify costs ~250 ms - and the
    endpoint becomes an account enumeration oracle even though both responses
    are byte-identical. See ``docs/logging_and_errors.md`` §3.
    """
    bcrypt.checkpw(b"", _dummy_hash())


# --- off-thread wrappers -----------------------------------------------------
#
# bcrypt at cost 12 burns ~230 ms of CPU. Called inline from an `async def`
# route it stalls the entire event loop for that long, so every other in-flight
# request waits - and `/auth/login` with a nonexistent login is reachable by any
# unauthenticated caller. Application code must use these; the sync functions
# above stay for tests and non-async callers.


async def hash_password_async(plain: str) -> str:
    return await to_thread.run_sync(hash_password, plain)


async def verify_password_async(plain: str, hashed: str) -> bool:
    return await to_thread.run_sync(verify_password, plain, hashed)


async def burn_password_time_async() -> None:
    await to_thread.run_sync(burn_password_time)


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
    logger.debug(
        "auth.access_token.issued",
        subject=str(data.get("sub")),
        expires_at=expire.isoformat(),
    )
    return encoded_jwt


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode a bearer token or raise a typed AuthError.

    Expiry gets its own code: the client has to tell "refresh me" apart from
    "this token is garbage". The token itself is never logged or echoed.
    """
    try:
        return jwt.decode(
            token,
            settings.security.secret_key,
            algorithms=[settings.security.algorithm],
        )
    except jwt.ExpiredSignatureError as ex:
        raise TokenExpiredError() from ex
    except jwt.PyJWTError as ex:
        raise InvalidTokenError() from ex


def create_token_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(
        days=settings.security.refresh_token_expire_days
    )


def create_refresh_token() -> str:
    return secrets.token_urlsafe(32)
