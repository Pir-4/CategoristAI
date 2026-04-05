import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import create_refresh_token, create_token_expires_at
from app.models import RefreshToken

logger = logging.getLogger(__name__)


async def save_refresh_token(session: AsyncSession, user_id: UUID) -> str:
    logger.info("Creating refresh token for user with id: %s", user_id)
    new_token = RefreshToken(
        token=create_refresh_token(),
        user_id=user_id,
        expires_at=create_token_expires_at(),
    )
    session.add(new_token)
    await session.commit()
    await session.refresh(new_token)
    return new_token.token


async def find_refresh_token(
    session: AsyncSession, token: str
) -> RefreshToken | None:
    logger.info("Get refresh token")
    return await session.get(RefreshToken, token)


async def delete_refresh_token(session: AsyncSession, token: RefreshToken):
    logger.info("Delete refresh token")
    await session.delete(token)
    await session.commit()
