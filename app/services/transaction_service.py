import time
from dataclasses import dataclass, field
from uuid import UUID

import structlog
from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ErrorCode, elapsed_ms
from app.core.exceptions import (
    AppError,
    DuplicateIdentityInBatchError,
    DuplicateTransactionError,
    TransactionCategoryNotFoundError,
    TransactionNotFoundError,
    TransactionPersistError,
)
from app.models import Account, Transaction, User
from app.schemas import TransactionUpdate
from app.schemas.upload import UploadIssue
from app.services.category_service import get_category_by_id
from app.services.csv_service import identity_key
from app.services.institution_parser import ParsedTransaction


def full_identity_key(transaction: Transaction) -> tuple:
    """The identity columns plus occurrence — mirrors the unique constraint."""
    return (*identity_key(transaction), transaction.occurrence)


logger = structlog.get_logger(__name__)

# PostgreSQL SQLSTATEs. An edit can break two different constraints and the
# client deserves to know which: an unknown category is not a duplicate.
_UNIQUE_VIOLATION = "23505"
_FOREIGN_KEY_VIOLATION = "23503"


def _sqlstate(ex: IntegrityError) -> str | None:
    """Pull the SQLSTATE out of whichever driver exception is underneath."""
    orig = ex.orig
    for candidate in (orig, getattr(orig, "__cause__", None)):
        state = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if state:
            return str(state)
    return None


@dataclass(slots=True)
class SaveReport:
    saved: list[Transaction] = field(default_factory=list)
    duplicates: list[UploadIssue] = field(default_factory=list)


async def get_transactions(
    session: AsyncSession,
    user: User,
) -> list[Transaction]:
    # user_id comes from contextvars (bound by get_current_user).
    result = await session.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user.id)
    )
    transactions = list(result.scalars().all())
    logger.debug("transactions.listed", count=len(transactions))
    return transactions


async def get_transaction_by_id(
    transaction_id: UUID,
    session: AsyncSession,
    user: User,
) -> Transaction | None:
    """One transaction, scoped to the accounts this user owns.

    The join is the authorisation check: somebody else's transaction and a
    non-existent one are the same answer, so the id cannot be probed.
    """
    result = await session.execute(
        select(Transaction)
        .join(Account, Transaction.account_id == Account.id)
        .where(Account.user_id == user.id)
        .where(Transaction.id == transaction_id)
    )
    transaction = result.scalar_one_or_none()
    logger.debug(
        "transaction.get",
        transaction_id=str(transaction_id),
        found=transaction is not None,
    )
    return transaction


async def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    session: AsyncSession,
    user: User,
) -> Transaction:
    """Apply a partial update. Raises TransactionNotFoundError if there is none.

    The not-found branch raises rather than returning None so the outcome is
    logged here, where the id and the requested fields are - the endpoint only
    ever sees an absence.
    """
    started = time.perf_counter()
    payload = data.model_dump(exclude_none=True)
    changed_fields = sorted(payload)
    log = logger.bind(transaction_id=str(transaction_id))
    log.info("transaction.update.started", fields=changed_fields)

    transaction = await get_transaction_by_id(transaction_id, session, user)
    if not transaction:
        error = TransactionNotFoundError(transaction_id=str(transaction_id))
        log.warning(
            "transaction.update.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error

    if not payload:
        # Every field was None, so there is nothing to apply. Skip the commit
        # and the refresh - a round trip and a SELECT that change nothing -
        # and, more importantly, do not log this as an update that happened.
        # The fetch above still ran: the response body needs the row, and an
        # unknown id must still be a 404 no matter how empty the body is.
        log.info(
            "transaction.update.skipped",
            reason="empty_payload",
            duration_ms=elapsed_ms(started),
        )
        return transaction

    category_id = payload.get("category_id")
    if category_id is not None and not await get_category_by_id(
        session, user, category_id
    ):
        error = TransactionCategoryNotFoundError(category_id=str(category_id))
        log.warning(
            "transaction.update.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error

    for key, value in payload.items():
        setattr(transaction, key, value)

    try:
        await session.commit()
    except IntegrityError as ex:
        await session.rollback()
        state = _sqlstate(ex)
        conflict: AppError
        if state == _FOREIGN_KEY_VIOLATION:
            # The only FK the payload can move is category_id, and it was
            # checked above - so reaching here means the category was deleted
            # between that check and this commit. Same answer for the caller.
            conflict = TransactionCategoryNotFoundError(
                category_id=str(payload.get("category_id"))
            )
        elif state == _UNIQUE_VIOLATION:
            # Editing the merchant can collide with the transaction identity
            # constraint (account_id, start_date, merchant, amount, fee,
            # occurrence).
            conflict = DuplicateTransactionError(fields=changed_fields)
        else:
            # An unknown constraint: we cannot say what the user did
            # wrong, so this is ours - it becomes a 500. No exc_info here:
            # the traceback is logged once, by http.unhandled_exception at
            # the outer edge. This line carries what that one cannot see -
            # the transaction, the fields, the SQLSTATE - and the two are
            # joined by request_id.
            log.error(
                "transaction.update.failed",
                fields=changed_fields,
                sqlstate=state,
            )
            raise
        log.warning(
            "transaction.update.rejected",
            duration_ms=elapsed_ms(started),
            **conflict.log_fields(),
        )
        raise conflict from ex

    await session.refresh(transaction)
    log.info(
        "transaction.updated",
        account_id=str(transaction.account_id),
        fields=changed_fields,
        duration_ms=elapsed_ms(started),
    )
    return transaction


async def save_transactions(
    session: AsyncSession, user: User, parsed: list[ParsedTransaction]
) -> SaveReport:
    """Persist the parsed rows, skipping ones already in the database."""
    started = time.perf_counter()
    logger.debug("transactions.save.started", candidates=len(parsed))

    by_identity: dict[tuple, ParsedTransaction] = {}
    for item in parsed:
        key = full_identity_key(item.transaction)
        existing = by_identity.get(key)
        if existing is not None:
            # Occurrence numbering makes this impossible; if it fires, the
            # numbering in parse_transactions is broken, not the user's file.
            raise DuplicateIdentityInBatchError(
                row_a=existing.row.number, row_b=item.row.number
            )
        by_identity[key] = item

    identity_columns = (
        Transaction.account_id,
        Transaction.start_date,
        Transaction.merchant,
        Transaction.amount,
        Transaction.fee,
        Transaction.occurrence,
    )
    result = await session.execute(
        select(*identity_columns).where(
            tuple_(*identity_columns).in_(by_identity.keys())
        )
    )
    existing_keys = {tuple(row) for row in result.all()}
    logger.debug(
        "transactions.dedup.checked",
        candidates=len(by_identity),
        existing=len(existing_keys),
    )

    report = SaveReport()
    new_transactions: list[Transaction] = []
    for key, item in by_identity.items():
        if key in existing_keys:
            report.duplicates.append(
                UploadIssue(
                    row_number=item.row.number,
                    line_number=item.row.line,
                    code=ErrorCode.DUPLICATE_TRANSACTION,
                    message="Transaction already imported",
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
        duration_ms=elapsed_ms(started),
    )
    return report
