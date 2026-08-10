from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, User
from app.schemas import AccountCreate

logger = structlog.get_logger(__name__)


async def create_account(
    session: AsyncSession,
    data: AccountCreate,
    user: User,
) -> Account:
    logger.info("Creating account with name: %s", data.name)
    new_account = Account(
        user_id=user.id,
        name=data.name,
        institution=data.institution,
        institution_acc_name=data.institution_acc_name,
    )
    session.add(new_account)
    await session.commit()
    await session.refresh(new_account)
    return new_account


async def get_accounts(
    session: AsyncSession,
    user: User,
) -> list[Account]:
    logger.info(f"Get account for user {user.id}")
    result = await session.execute(
        select(Account).where(Account.user_id == user.id)
    )
    return list(result.scalars().all())


async def get_account_by_id(
    session: AsyncSession,
    user: User,
    account_id: UUID,
) -> Account | None:
    logger.info(f"Get account by id {account_id} for user {user.id}")
    result = await session.execute(
        select(Account).where(
            Account.user_id == user.id, Account.id == account_id
        )
    )
    return result.scalar_one_or_none()
