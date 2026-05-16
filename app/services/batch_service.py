from uuid import UUID

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    TransactionStatus,
    TransactionType,
)
from app.models import Batch, Transaction

logger = structlog.get_logger(__name__)


async def create_batch(
    transactions: list[Transaction],
    account_id: UUID,
    session: AsyncSession,
) -> Batch:
    logger.info("Create batch")
    new_batch = Batch(account_id=account_id)
    session.add(new_batch)
    await session.flush()
    await session.refresh(new_batch)
    new_batch.total_count = await create_transactions(
        transactions=transactions, batch=new_batch, session=session
    )
    await session.commit()
    return new_batch


async def create_transactions(
    transactions: list[Transaction],
    batch: Batch,
    session: AsyncSession,
) -> int:
    logger.info("Create transactions")
    inserted = 0
    for transaction in transactions:
        transaction.batch_id = batch.id
        transaction.status = identify_transaction_status(transaction)
        try:
            async with session.begin_nested():
                session.add(transaction)
            inserted += 1
        except IntegrityError:
            logger.warning(
                f"Duplicate transaction skipped: {transaction.dedup_hash}"
            )
            continue
    return inserted


def identify_transaction_status(transaction: Transaction) -> TransactionStatus:
    if transaction.transaction_type in [
        TransactionType.INCOME,
        TransactionType.INTERNAL_TRANSFER,
    ]:
        return TransactionStatus.REVIEWED
    return TransactionStatus.PENDING
