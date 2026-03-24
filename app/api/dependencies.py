from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import AsyncSession, decode_access_token, get_session
from app.models import User
from app.services.user_service import get_user

oauth2_scheme = HTTPBearer()


async def get_current_user(
    token: HTTPAuthorizationCredentials = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token.credentials)
        user_id = payload.get("sub")
        user = await get_user(session, UUID(user_id))
    except ValueError as ex:
        raise credentials_error from ex

    if not user:
        raise credentials_error
    return user
