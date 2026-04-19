import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Expense

logger = logging.getLogger(__name__)


async def create_batch(
    expenses: list[Expense],
    session: AsyncSession,
) -> Batch:
    logger.info("Create batch")
    new_batch = Batch()
    session.add(new_batch)
    await session.flush()
    await session.refresh(new_batch)
    new_batch.total_count = await create_expense(
        expenses=expenses, batch=new_batch, session=session
    )
    await session.commit()
    return new_batch


async def create_expense(
    expenses: list[Expense],
    batch: Batch,
    session: AsyncSession,
) -> int:
    logger.info("Create expenses")
    inserted = 0
    for expense in expenses:
        expense.batch_id = batch.id
        try:
            async with session.begin_nested():
                session.add(expense)
            inserted += 1
        except IntegrityError:
            logger.warning(f"Duplicate expense skipped: {expense.dedup_hash}")
            continue
    return inserted
