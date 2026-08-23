from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models import Account, Transaction, User
from app.schemas import TransactionUpdate

logger = structlog.get_logger(__name__)


async def get_transactions(
    session: AsyncSession,
    user: User,
) -> list[Transaction]:
    logger.info(f"Get transactions for user {user.id}")
    result = await session.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user.id)
    )
    return list(result.scalars().all())


async def get_transaction_by_id(
    transaction_id: UUID,
    session: AsyncSession,
    user: User,
) -> Transaction | None:
    logger.info(f"Get transaction for user {user.id} by id {transaction_id}")
    result = await session.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user.id)
        .where(Transaction.id == transaction_id)
    )
    return result.scalar_one_or_none()


async def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    session: AsyncSession,
    user: User,
) -> Transaction | None:
    logger.info(f"Update transaction for user {user.id} by id {transaction_id}")
    transaction = await get_transaction_by_id(transaction_id, session, user)
    if not transaction:
        return None

    for key, value in data.model_dump(exclude_none=True).items():
        setattr(transaction, key, value)

    await session.commit()
    await session.refresh(transaction)
    return transaction


async def save_transactions(
    session: AsyncSession, user: User, transactions: list[Transaction]
) -> list[Transaction]:
    logger.info(f"Save transactions for user {user.id}")
    for tr in transactions:
        try:
            session.add(tr)
            await session.flush()  # проставит id и defaults
        except IntegrityError:
            # dedup_hash дубль — пропускаем
            pass
            # await session.rollback()  # или begin_nested

    await session.commit()
    return transactions
