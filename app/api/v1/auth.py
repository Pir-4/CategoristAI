from http import HTTPStatus

from fastapi import Depends, HTTPException
from fastapi.routing import APIRouter

from app.core import (
    AsyncSession,
    create_access_token,
    get_session,
    verify_password,
)
from app.schemas import LoginRequest, TokenResponse, UserCreate
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
    new_user = await svc_create_user(session=session, data=user)
    token = create_access_token({"sub": str(new_user.id)})
    return TokenResponse(access_token=token)


@router.post("/login")
async def login_user(
    r_login: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    user = await svc_get_user_by_login(session, login=r_login.login)
    if not user or not verify_password(r_login.password, user.hashed_password):
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="User or password are incorrect",
        )
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout_user():
    return {"message": "Successfully logged out"}
