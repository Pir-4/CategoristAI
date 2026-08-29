import time
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ErrorCode
from app.core.exceptions import (
    DedupHashCollisionError,
    TransactionPersistError,
)
from app.models import Account, Transaction, User
from app.schemas import TransactionUpdate
from app.schemas.upload import UploadIssue
from app.services.institution_parser import ParsedTransaction

logger = structlog.get_logger(__name__)


@dataclass(slots=True)
class SaveReport:
    saved: list[Transaction] = field(default_factory=list)
    duplicates: list[UploadIssue] = field(default_factory=list)


async def get_transactions(
    session: AsyncSession,
    user: User,
) -> list[Transaction]:
    logger.debug("transactions.list", user_id=str(user.id))
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
    logger.debug(
        "transactions.get",
        user_id=str(user.id),
        transaction_id=str(transaction_id),
    )
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
    logger.info(
        "transactions.update",
        user_id=str(user.id),
        transaction_id=str(transaction_id),
    )
    transaction = await get_transaction_by_id(transaction_id, session, user)
    if not transaction:
        return None

    for key, value in data.model_dump(exclude_none=True).items():
        setattr(transaction, key, value)

    await session.commit()
    await session.refresh(transaction)
    return transaction


async def save_transactions(
    session: AsyncSession, user: User, parsed: list[ParsedTransaction]
) -> SaveReport:
    """Persist the parsed rows, skipping ones already in the database."""
    started = time.perf_counter()
    logger.debug("transactions.save.started", candidates=len(parsed))

    by_hash: dict[str, ParsedTransaction] = {}
    for item in parsed:
        dedup_hash = item.transaction.dedup_hash
        existing = by_hash.get(dedup_hash)
        if existing is not None:
            # Occurrence counting makes this impossible; if it fires it is
            # a bug in build_dedup_hash, not bad user data.
            raise DedupHashCollisionError(
                dedup_hash=dedup_hash,
                row_a=existing.row.number,
                row_b=item.row.number,
            )
        by_hash[dedup_hash] = item

    result = await session.execute(
        select(Transaction.dedup_hash).where(
            Transaction.dedup_hash.in_(by_hash.keys())
        )
    )
    existing_hashes = set(result.scalars().all())
    logger.debug(
        "transactions.dedup.checked",
        candidates=len(by_hash),
        existing=len(existing_hashes),
    )

    report = SaveReport()
    new_transactions: list[Transaction] = []
    for dedup_hash, item in by_hash.items():
        if dedup_hash in existing_hashes:
            report.duplicates.append(
                UploadIssue(
                    row_number=item.row.number,
                    line_number=item.row.line,
                    code=ErrorCode.DUPLICATE_TRANSACTION,
                    message="Transaction already imported",
                    details={"dedup_hash": dedup_hash},
                )
            )
            continue
        new_transactions.append(item.transaction)

    session.add_all(new_transactions)
    try:
        await session.commit()
    except SQLAlchemyError as ex:
        await session.rollback()
        logger.exception(
            "transactions.persist_failed", batch_size=len(new_transactions)
        )
        raise TransactionPersistError(batch_size=len(new_transactions)) from ex

    report.saved = new_transactions
    logger.info(
        "transactions.saved",
        saved=len(report.saved),
        duplicates=len(report.duplicates),
        user_id=str(user.id),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return report
