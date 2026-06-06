from fastapi import Depends
from fastapi.routing import APIRouter

from app.api.dependencies import get_current_user
from app.core import AsyncSession, get_session
from app.models import User
from app.schemas import AccountCreate, AccountResponse
from app.services.account_service import (
    create_account as svc_create_account,
)
from app.services.account_service import (
    get_account as svc_get_account,
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
