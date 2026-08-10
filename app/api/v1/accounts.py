from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from uuid import UUID

from app.api.dependencies import get_current_user
from app.core import AsyncSession, get_session
from app.models import User
from app.schemas import AccountCreate, AccountResponse, AccountUpdate
from app.services.account_service import (
    create_account as svc_create_account,
    get_accounts as svc_get_account,
    update_account as svc_update_account,
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
async def get_accounts(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[AccountResponse]:
    accounts = await svc_get_account(session=session, user=user)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.patch("/{account_id}")
async def update_account(
    account_id: UUID,
    data: AccountUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = await svc_update_account(
        account_id, data=data, session=session, user=user
    )
    if not account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account not found",
        )
    return AccountResponse.model_validate(account)
