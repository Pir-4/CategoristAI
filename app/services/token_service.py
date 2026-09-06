"""Refresh token lifecycle.

The refresh token *is* the primary key of the row, so there is no jti to log.
Every line here therefore identifies a token by ``token_fp`` - the truncated
SHA-256 from ``app.core.logging.fingerprint``. It correlates issue -> use ->
revoke across the logs and cannot be turned back into the secret.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    create_refresh_token,
    create_token_expires_at,
    fingerprint,
)
from app.core.exceptions import InvalidRefreshTokenError, TokenExpiredError
from app.models import RefreshToken

logger = structlog.get_logger(__name__)


async def save_refresh_token(session: AsyncSession, user_id: UUID) -> str:
    new_token = RefreshToken(
        token=create_refresh_token(),
        user_id=user_id,
        expires_at=create_token_expires_at(),
    )
    session.add(new_token)
    await session.commit()
    await session.refresh(new_token)
    logger.info(
        "auth.refresh_token.issued",
        user_id=str(user_id),
        token_fp=fingerprint(new_token.token),
        expires_at=new_token.expires_at.isoformat(),
    )
    return new_token.token


async def find_refresh_token(
    session: AsyncSession, token: str
) -> RefreshToken | None:
    db_token = await session.get(RefreshToken, token)
    logger.debug(
        "auth.refresh_token.lookup",
        token_fp=fingerprint(token),
        found=db_token is not None,
    )
    return db_token


async def require_refresh_token(
    session: AsyncSession, token: str
) -> RefreshToken:
    """Return a usable refresh token or raise.

    Both rejections are the caller's problem, not a bug: an unknown token
    (never issued, already rotated, or logged out) and an expired one. They
    get different codes so the client knows whether to re-login.
    """
    token_fp = fingerprint(token)
    db_token = await find_refresh_token(session, token)

    if db_token is None:
        error = InvalidRefreshTokenError()
        logger.warning(
            "auth.refresh_token.rejected",
            reason="unknown",
            token_fp=token_fp,
            **error.log_fields(),
        )
        raise error

    if db_token.expires_at < datetime.now(UTC):
        error = TokenExpiredError()
        logger.warning(
            "auth.refresh_token.rejected",
            reason="expired",
            token_fp=token_fp,
            user_id=str(db_token.user_id),
            expires_at=db_token.expires_at.isoformat(),
            **error.log_fields(),
        )
        raise error

    return db_token


async def delete_refresh_token(session: AsyncSession, token: RefreshToken):
    token_fp = fingerprint(token.token)
    user_id = str(token.user_id)
    await session.delete(token)
    await session.commit()
    logger.info(
        "auth.refresh_token.revoked",
        user_id=user_id,
        token_fp=token_fp,
    )
