from uuid import UUID

from fastapi import Depends
from fastapi.routing import APIRouter

from app.api.dependencies import get_current_user
from app.core import AsyncSession, get_session
from app.models import User
from app.schemas import TransactionResponse, TransactionUpdate
from app.services.transaction_service import (
    get_transactions as svc_get_transactions,
)
from app.services.transaction_service import (
    update_transaction as svc_update_transaction,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
async def get_transactions(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TransactionResponse]:
    transactions = await svc_get_transactions(session=session, user=user)
    return [TransactionResponse.model_validate(t) for t in transactions]


@router.patch("/{transaction_id}")
async def update_transaction(
    transaction_id: UUID,
    data: TransactionUpdate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TransactionResponse:
    transaction = await svc_update_transaction(
        transaction_id, data=data, session=session, user=user
    )
    return TransactionResponse.model_validate(transaction)
