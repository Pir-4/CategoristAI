import time
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import elapsed_ms
from app.core.exceptions import (
    AccountNameAlreadyTakenError,
    AccountNotFoundError,
)
from app.models import Account, User
from app.schemas import AccountCreate, AccountUpdate

logger = structlog.get_logger(__name__)


async def create_account(
    session: AsyncSession,
    data: AccountCreate,
    user: User,
) -> Account:
    """Create an account. Name uniqueness is decided by the database.

    A pre-check would not hold - two concurrent requests both pass it - so the
    unique constraint on (user_id, name) is what actually decides, and the
    IntegrityError is translated here instead of reaching the client as a 500
    with a stacktrace.
    """
    started = time.perf_counter()
    # user_id comes from contextvars (bound by get_current_user).
    logger.info(
        "account.create.started",
        name=data.name,
        institution=str(data.institution),
        institution_acc_name=data.institution_acc_name,
    )

    new_account = Account(
        user_id=user.id,
        name=data.name,
        institution=data.institution,
        institution_acc_name=data.institution_acc_name,
    )
    session.add(new_account)
    try:
        await session.commit()
    except IntegrityError as ex:
        await session.rollback()
        # The only constraint reachable here is (user_id, name): the user_id
        # FK is satisfied by the authenticated caller.
        error = AccountNameAlreadyTakenError(name=data.name)
        logger.warning(
            "account.create.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error from ex

    await session.refresh(new_account)
    logger.info(
        "account.created",
        account_id=str(new_account.id),
        name=new_account.name,
        institution=str(new_account.institution),
        duration_ms=elapsed_ms(started),
    )
    return new_account


async def get_accounts(
    session: AsyncSession,
    user: User,
) -> list[Account]:
    result = await session.execute(
        select(Account).where(Account.user_id == user.id)
    )
    accounts = list(result.scalars().all())
    logger.debug("accounts.listed", count=len(accounts))
    return accounts


async def get_account_by_id(
    session: AsyncSession,
    user: User,
    account_id: UUID,
) -> Account | None:
    """Look up one of this user's accounts. None means "not theirs, or gone".

    Returning None rather than raising keeps the verdict with the caller: the
    upload flow and the accounts endpoints both want a 404, but they word the
    surrounding log line differently.
    """
    result = await session.execute(
        select(Account).where(
            Account.user_id == user.id, Account.id == account_id
        )
    )
    account = result.scalar_one_or_none()
    logger.debug(
        "account.get", account_id=str(account_id), found=account is not None
    )
    return account


async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    session: AsyncSession,
    user: User,
) -> Account:
    """Apply a partial update. Raises AccountNotFoundError if there is none.

    The not-found branch raises instead of returning None so that the outcome
    is logged where the fields are - the endpoint would only see an absence.
    """
    started = time.perf_counter()
    payload = data.model_dump(exclude_none=True)
    changed_fields = sorted(payload)
    logger.info("account.update.started", fields=changed_fields)

    account = await get_account_by_id(session, user, account_id)
    if not account:
        error = AccountNotFoundError(account_id=str(account_id))
        logger.warning(
            "account.update.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error

    if not payload:
        # Nothing to apply - skip the commit and the refresh, and do not log
        # this as an update that happened. The fetch above still ran: an
        # unknown id is a 404 however empty the body is.
        logger.info(
            "account.update.skipped",
            reason="empty_payload",
            duration_ms=elapsed_ms(started),
        )
        return account

    for key, value in payload.items():
        setattr(account, key, value)

    try:
        await session.commit()
    except IntegrityError as ex:
        await session.rollback()
        error = AccountNameAlreadyTakenError(name=payload.get("name"))
        logger.warning(
            "account.update.rejected",
            duration_ms=elapsed_ms(started),
            **error.log_fields(),
        )
        raise error from ex

    await session.refresh(account)
    logger.info(
        "account.updated",
        fields=changed_fields,
        duration_ms=elapsed_ms(started),
    )
    return account
