from fastapi import Depends, HTTPException, status, UploadFile
from fastapi.routing import APIRouter
from uuid import UUID

from app.models import User
from app.schemas import BatchResponse
from app.core import AsyncSession, get_session
from app.api.dependencies import get_current_user
from app.services.bank_parser import Banks
from app.services.account_service import (
    get_account_by_id,
    get_accounts,
)
from app.services.csv_service import parse_transactions
from app.services import batch_service

router = APIRouter(prefix="/uploads", tags=["uploads"])


@router.post("")
async def upload_batch(
    upload_file: UploadFile,
    account_id: UUID,
    bank: Banks,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BatchResponse:
    current_account = await get_account_by_id(
        session=session, user=user, account_id=account_id
    )
    if not current_account:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
        )
    user_accounts = await get_accounts(session, user)
    transactions = await parse_transactions(
        upload_file, bank=bank, accounts=user_accounts
    )
    batch = await batch_service.create_batch(transactions, account_id, session)
    return BatchResponse.model_validate(batch)
