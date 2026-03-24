import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import hash_password
from app.models import User
from app.schemas import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    logger.info("Get user by id: %s", user_id)
    return await session.get(User, user_id)


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    logger.info("Get user by login: %s", login)
    result = await session.execute(select(User).where(User.login == login))
    return result.scalar_one_or_none()


async def get_users(session: AsyncSession) -> list[User]:
    logger.info("Get all users")
    result = await session.execute(select(User))
    return list(result.scalars().all())


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    logger.info("Creating user with login: %s", data.login)
    new_user = User(
        login=data.login, hashed_password=hash_password(data.password)
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)
    return new_user


async def update_user(
    session: AsyncSession, user_id: UUID, data: UserUpdate
) -> User | None:
    logger.info("Updating user %s", user_id)
    user = await get_user(session, user_id)
    if not user:
        raise ValueError(f"User with id {user_id} not found")

    for key, value in data.model_dump(exclude_none=True).items():
        # TODO change logic
        if key == "password":
            user.hashed_password = hash_password(value)
        else:
            setattr(user, key, value)

    await session.commit()
    await session.refresh(user)
    return user
