from datetime import UTC, datetime

from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter

from app.api.dependencies import get_current_user
from app.core import (
    AsyncSession,
    create_access_token,
    get_session,
    verify_password,
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
    save_refresh_token,
)
from app.services.user_service import (
    create_user as svc_create_user,
)
from app.services.user_service import (
    get_user_by_login as svc_get_user_by_login,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
async def register_user(
    user: UserCreate, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    existing = await svc_get_user_by_login(session, login=user.login)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Login already taken"
        )
    new_user = await svc_create_user(session=session, data=user)
    access_token = create_access_token({"sub": str(new_user.id)})
    refresh_token = await save_refresh_token(session, new_user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login")
async def login_user(
    r_login: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    user = await svc_get_user_by_login(session, login=r_login.login)
    if not user or not verify_password(r_login.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User or password are incorrect",
        )
    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = await save_refresh_token(session, user.id)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout")
async def logout_user(
    r_refresh_token: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    db_rf_token = await find_refresh_token(
        session, r_refresh_token.refresh_token
    )
    if not db_rf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    await delete_refresh_token(session, db_rf_token)
    return {"message": "Successfully logged out"}


@router.post("/refresh")
async def refresh_token(
    r_refresh_token: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    db_rf_token = await find_refresh_token(
        session, r_refresh_token.refresh_token
    )
    if not db_rf_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    if db_rf_token.expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired"
        )
    await delete_refresh_token(session, db_rf_token)

    refresh_token = await save_refresh_token(session, db_rf_token.user_id)
    access_token = create_access_token({"sub": str(db_rf_token.user_id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)
