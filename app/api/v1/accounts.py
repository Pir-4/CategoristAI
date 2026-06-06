from fastapi import Depends, HTTPException, status, Response
from fastapi.routing import APIRouter
from uuid import UUID

from app.api.dependencies import get_current_user
from app.core import AsyncSession, get_session
from app.models import User
from app.schemas import (
    AccountCreate,
    AccountResponse,
    KeywordCreate,
    KeywordResponse,
)
from app.services.account_service import (
    create_account as svc_create_account,
    get_account as svc_get_account,
    get_account_by_id,
    create_keywords as svc_create_keywords,
    delete_keyword as svc_delete_keyword,
)

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.post("")
async def create_account(
    account: AccountCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    new_account = await svc_create_account(
        session=session, data=account, user=user
    )
    return AccountResponse.model_validate(new_account)


@router.get("")
async def get_account(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AccountResponse]:
    accounts = await svc_get_account(session=session, user=user)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.post("/{account_id}/keywords")
async def create_keywords(
    account_id: UUID,
    data: KeywordCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> KeywordResponse:
    account = await get_account_by_id(session, user, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    account_keywords = await svc_create_keywords(session, data, account)
    return KeywordResponse.model_validate(account_keywords)


@router.delete("/{account_id}/keywords/{keyword_id}")
async def delete_keywords(
    account_id: UUID,
    keyword_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    account = await get_account_by_id(session, user, account_id)
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    await svc_delete_keyword(session, keyword_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
