from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from uuid import UUID

from app.models import User
from app.schemas import TransactionResponse, TransactionUpdate
from app.core import AsyncSession, get_session
from app.api.dependencies import get_current_user
from app.services.transaction_service import (
    get_transactions as svc_get_transactions,
    update_transaction as svc_update_transaction,
    get_transaction_by_batch_id as svc_get_transaction_by_batch_id,
)

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.get("")
async def get_transactions(
    batch_id: UUID | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TransactionResponse]:
    if batch_id:
        transactions = await svc_get_transaction_by_batch_id(
            batch_id, session=session, user=user
        )
    else:
        transactions = await svc_get_transactions(session=session, user=user)
    return [TransactionResponse.model_validate(a) for a in transactions]


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
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )
    return TransactionResponse.model_validate(transaction)
