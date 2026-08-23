from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    # keep first occurrence if the incoming batch itself has duplicate hashes
    unique_by_hash: dict[str, Transaction] = {}
    for tr in transactions:
        if tr.dedup_hash in unique_by_hash:
            raise ValueError(
                f"Hash duplication in transaction list: "
                f"tr1 {unique_by_hash[tr.dedup_hash]}, tr2: {tr}"
            )
        unique_by_hash[tr.dedup_hash] = tr

    result = await session.execute(
        select(Transaction.dedup_hash).where(
            Transaction.dedup_hash.in_(unique_by_hash.keys())
        )
    )
    existing_hashes = set(result.scalars().all())

    new_transactions = [
        tr
        for dedup_hash, tr in unique_by_hash.items()
        if dedup_hash not in existing_hashes
    ]

    session.add_all(new_transactions)
    await session.commit()

    skipped = len(transactions) - len(new_transactions)
    logger.info(
        f"Saved {len(new_transactions)} transactions, "
        f"skipped {skipped} duplicates for user {user.id}"
    )
    return new_transactions
