import time

import structlog
from fastapi import Depends
from fastapi.routing import APIRouter

from app.api.dependencies import get_current_user
from app.core import (
    AsyncSession,
    burn_password_time_async,
    create_access_token,
    fingerprint,
    get_session,
    verify_password_async,
)
from app.core.exceptions import (
    InvalidCredentialsError,
    InvalidRefreshTokenError,
    LoginAlreadyTakenError,
)
from app.models import User
from app.schemas import (
    LoginRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
)
from app.services.token_service import (
    delete_refresh_token,
    find_refresh_token,
    require_refresh_token,
    save_refresh_token,
)
from app.services.user_service import (
    create_user as svc_create_user,
)
from app.services.user_service import (
    get_user_by_login as svc_get_user_by_login,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)


@router.post("/register")
async def register_user(
    user: UserCreate, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    started = time.perf_counter()
    logger.info("auth.register.started", login=user.login)

    existing = await svc_get_user_by_login(session, login=user.login)
    if existing:
        error = LoginAlreadyTakenError(login=user.login)
        logger.warning(
            "auth.register.rejected",
            duration_ms=_elapsed_ms(started),
            **error.log_fields(),
        )
        raise error

    new_user = await svc_create_user(session=session, data=user)
    structlog.contextvars.bind_contextvars(user_id=str(new_user.id))

    access_token = create_access_token({"sub": str(new_user.id)})
    refresh_token = await save_refresh_token(session, new_user.id)
    logger.info(
        "auth.register.completed",
        user_id=str(new_user.id),
        login=new_user.login,
        duration_ms=_elapsed_ms(started),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login")
async def login_user(
    r_login: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    """Authenticate a user.

    The response is deliberately identical for "no such login" and "wrong
    password" - anything else is a user-enumeration oracle. That includes how
    long it takes: the unknown-login branch burns the same bcrypt time rather
    than returning early. The *log* is specific, because the log is ours:
    `reason` tells the two apart.
    """
    started = time.perf_counter()
    logger.info("auth.login.started", login=r_login.login)

    user = await svc_get_user_by_login(session, login=r_login.login)
    if not user:
        # Pay the bcrypt cost we would have paid for a real account, so the
        # two failures cannot be told apart by response time either.
        await burn_password_time_async()
        logger.warning(
            "auth.login.failed",
            login=r_login.login,
            reason="user_unknown",
            duration_ms=_elapsed_ms(started),
            **InvalidCredentialsError().log_fields(),
        )
        raise InvalidCredentialsError()

    if not await verify_password_async(r_login.password, user.hashed_password):
        logger.warning(
            "auth.login.failed",
            login=r_login.login,
            user_id=str(user.id),
            reason="bad_password",
            duration_ms=_elapsed_ms(started),
            **InvalidCredentialsError().log_fields(),
        )
        raise InvalidCredentialsError()

    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = await save_refresh_token(session, user.id)
    logger.info(
        "auth.login.succeeded",
        user_id=str(user.id),
        login=user.login,
        duration_ms=_elapsed_ms(started),
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout")
async def logout_user(
    r_refresh_token: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Revoke one refresh token belonging to the caller.

    Deliberately tolerant of expiry, unlike `/auth/refresh`: the point here is
    to remove the row, and refusing to delete an expired token would strand it
    in the table forever with no way for the client to clean it up.

    A token may only be revoked by its owner - otherwise any authenticated
    caller can end anyone else's session by presenting their token. "Unknown"
    and "not yours" answer identically, so the endpoint cannot be used to probe
    which tokens exist; only the log tells them apart.
    """
    started = time.perf_counter()
    token_fp = fingerprint(r_refresh_token.refresh_token)
    db_rf_token = await find_refresh_token(
        session, r_refresh_token.refresh_token
    )

    if db_rf_token is None or db_rf_token.user_id != current_user.id:
        error = InvalidRefreshTokenError()
        logger.warning(
            "auth.logout.rejected",
            reason="unknown" if db_rf_token is None else "not_owner",
            token_fp=token_fp,
            duration_ms=_elapsed_ms(started),
            **error.log_fields(),
        )
        raise error

    await delete_refresh_token(session, db_rf_token)
    logger.info("auth.logout.completed", duration_ms=_elapsed_ms(started))
    return {"message": "Successfully logged out"}


@router.post("/refresh")
async def refresh_token(
    r_refresh_token: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    started = time.perf_counter()
    presented_fp = fingerprint(r_refresh_token.refresh_token)
    logger.info("auth.refresh.started", token_fp=presented_fp)

    db_rf_token = await require_refresh_token(
        session, r_refresh_token.refresh_token
    )
    user_id = db_rf_token.user_id
    structlog.contextvars.bind_contextvars(user_id=str(user_id))

    # Rotation: the presented token dies before the new one is handed out.
    await delete_refresh_token(session, db_rf_token)
    new_refresh_token = await save_refresh_token(session, user_id)
    access_token = create_access_token({"sub": str(user_id)})

    logger.info(
        "auth.refresh.completed",
        user_id=str(user_id),
        rotated_from_fp=presented_fp,
        rotated_to_fp=fingerprint(new_refresh_token),
        duration_ms=_elapsed_ms(started),
    )
    return TokenResponse(
        access_token=access_token, refresh_token=new_refresh_token
    )
