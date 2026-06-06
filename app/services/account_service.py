import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, AccountKeyword, User
from app.schemas import AccountCreate, KeywordCreate

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
        account_type=data.account_type,
        initial_balance=data.initial_balance,
        is_categorizable=data.is_categorizable,
    )
    session.add(new_account)
    await session.flush()
    await session.refresh(new_account)
    for kw in data.keywords:
        session.add(
            AccountKeyword(account_id=new_account.id, keyword=kw.keyword)
        )
    await session.commit()
    await session.refresh(new_account)
    return new_account


async def create_keywords(
    session: AsyncSession, data: KeywordCreate, account: Account
) -> AccountKeyword:
    logger.info(f"Creating keyword {data.keyword} for account {account.id}")
    new_keyword = AccountKeyword(
        account_id=account.id,
        keyword=data.keyword,
    )
    session.add(new_keyword)
    await session.commit()
    await session.refresh(new_keyword)
    return new_keyword


async def get_account(
    session: AsyncSession,
    user: User,
) -> list[Account]:
    logger.info(f"Get account for user {user.id}")
    result = await session.execute(
        select(Account).where(Account.user_id == user.id)
    )
    return list(result.scalars().all())
