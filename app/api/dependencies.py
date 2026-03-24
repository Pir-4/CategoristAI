from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.core import AsyncSession, decode_access_token, get_session
from app.models import User
from app.services.user_service import get_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
    except ValueError as ex:
        raise credentials_error from ex

    user_id = payload.get("sub")
    user = await get_user(session, user_id)
    if not user:
        raise credentials_error
    return user
