from uuid import UUID

import structlog
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import AsyncSession, UserRole, decode_access_token, get_session
from app.core.exceptions import (
    AuthError,
    InvalidTokenError,
    PermissionDeniedError,
    TokenExpiredError,
)
from app.models import User
from app.services.user_service import get_user

logger = structlog.get_logger(__name__)

oauth2_scheme = HTTPBearer()


async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the bearer token to a user.

    Every rejection is logged with a specific `reason` while the client only
    ever sees the generic code - the reason tells us which of four different
    problems it was, and the token itself is never logged.
    """
    try:
        payload = decode_access_token(token.credentials)
    except AuthError as ex:
        # Re-raised unchanged; logged here so that all four rejection
        # reasons are greppable under one event name.
        reason = (
            "expired" if isinstance(ex, TokenExpiredError) else "decode_failed"
        )
        logger.warning("auth.token.rejected", reason=reason, **ex.log_fields())
        raise

    subject = payload.get("sub")
    if not subject:
        logger.warning("auth.token.rejected", reason="missing_subject")
        raise InvalidTokenError()

    try:
        user_id = UUID(str(subject))
    except ValueError as ex:
        # A token we signed whose `sub` is not a UUID: it validated, so this
        # is either an old format or our bug - either way not a crash.
        logger.warning("auth.token.rejected", reason="malformed_subject")
        raise InvalidTokenError() from ex

    user = await get_user(session, user_id)
    if not user:
        # Valid signature, but the account is gone (deleted, or another
        # environment's database).
        logger.warning(
            "auth.token.rejected",
            reason="user_not_found",
            user_id=str(user_id),
        )
        raise InvalidTokenError()

    # Every log line in every endpoint gets attributed from here on.
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    logger.debug("auth.authenticated", role=str(user.role))
    return user


async def check_admin_permission(
    user: User = Depends(get_current_user),
) -> User:
    if user.role != UserRole.ADMIN:
        error = PermissionDeniedError()
        logger.warning(
            "auth.permission.denied",
            role=str(user.role),
            required_role=str(UserRole.ADMIN),
            **error.log_fields(),
        )
        raise error
    return user
