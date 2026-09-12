import time
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import elapsed_ms, hash_password_async
from app.core.exceptions import (
    LoginAlreadyTakenError,
    UnexpectedUpdateFieldError,
    UserNotFoundError,
)
from app.models import User
from app.schemas import UserCreate, UserUpdate

logger = structlog.get_logger(__name__)


async def get_user(session: AsyncSession, user_id: UUID) -> User | None:
    logger.debug("user.get", user_id=str(user_id))
    return await session.get(User, user_id)


async def get_user_by_login(session: AsyncSession, login: str) -> User | None:
    logger.debug("user.get_by_login", login=login)
    result = await session.execute(select(User).where(User.login == login))
    return result.scalar_one_or_none()


async def get_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User))
    users = list(result.scalars().all())
    logger.debug("users.listed", count=len(users))
    return users


async def create_user(session: AsyncSession, data: UserCreate) -> User:
    """Create a user. The login uniqueness verdict belongs to the database.

    A pre-check in the endpoint cannot be trusted on its own - two concurrent
    registrations both pass it - so the IntegrityError is what actually
    decides, and it is translated here rather than reaching the client as a
    500 with a stacktrace.
    """
    started = time.perf_counter()
    logger.info("user.create.started", login=data.login)

    new_user = User(
        login=data.login,
        hashed_password=await hash_password_async(data.password),
    )
    session.add(new_user)
    try:
        await session.commit()
    except IntegrityError as ex:
        await session.rollback()
        error = LoginAlreadyTakenError(login=data.login)
        logger.warning(
            "user.create.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error from ex

    await session.refresh(new_user)
    logger.info(
        "user.created",
        user_id=str(new_user.id),
        login=new_user.login,
        role=str(new_user.role),
        duration_ms=elapsed_ms(started),
    )
    return new_user


async def update_user(
    session: AsyncSession, user_id: UUID, data: UserUpdate
) -> User:
    """Apply a partial update. Raises UserNotFoundError if there is no user."""
    started = time.perf_counter()
    payload = data.model_dump(exclude_none=True)
    # Field *names* only: the values include the new plaintext password.
    changed_fields = sorted(payload)
    logger.info(
        "user.update.started", user_id=str(user_id), fields=changed_fields
    )

    user = await get_user(session, user_id)
    if not user:
        error = UserNotFoundError(user_id=str(user_id))
        logger.warning("user.update.rejected", **error.log_fields())
        raise error

    for key, value in payload.items():
        if key == "password":
            user.hashed_password = await hash_password_async(value)
        elif hasattr(user, key):
            setattr(user, key, value)
        else:
            # A field was added to UserUpdate with nothing here to apply it.
            # That is our bug, so it fails loud instead of silently no-oping.
            raise UnexpectedUpdateFieldError(
                field_name=key, user_id=str(user_id)
            )

    try:
        await session.commit()
    except IntegrityError as ex:
        await session.rollback()
        error = LoginAlreadyTakenError(login=payload.get("login"))
        logger.warning(
            "user.update.rejected",
            user_id=str(user_id),
            **error.log_fields(),
        )
        raise error from ex

    await session.refresh(user)
    logger.info(
        "user.updated",
        user_id=str(user.id),
        fields=changed_fields,
        password_changed="password" in payload,
        duration_ms=elapsed_ms(started),
    )
    return user
