from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, User

logger = structlog.get_logger(__name__)


async def get_category_by_id(
    session: AsyncSession,
    user: User,
    category_id: UUID,
) -> Category | None:
    """Look up one of this user's categories. None means "not theirs, or gone".

    The ``user_id`` predicate is the authorisation check, not a convenience: a
    foreign key only asserts that the row exists *somewhere*, so without it a
    caller could attach another user's category to their own transaction.
    Somebody else's category and a non-existent one give the same answer, so
    ids cannot be probed either.
    """
    result = await session.execute(
        select(Category).where(
            Category.user_id == user.id, Category.id == category_id
        )
    )
    category = result.scalar_one_or_none()
    logger.debug(
        "category.get",
        category_id=str(category_id),
        found=category is not None,
    )
    return category
