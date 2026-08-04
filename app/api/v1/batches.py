from fastapi import Depends, HTTPException, status
from fastapi.routing import APIRouter
from uuid import UUID

from app.models import User
from app.schemas import BatchResponse
from app.core import AsyncSession, get_session
from app.api.dependencies import get_current_user
from app.services.batch_service import (
    get_batches as svc_get_batches,
    get_batch_by_id as svc_get_batch_by_id,
)

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("")
async def get_batches(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[BatchResponse]:
    batches = await svc_get_batches(session=session, user=user)
    return [BatchResponse.model_validate(a) for a in batches]


@router.get("/{batch_id}")
async def get_batch_by_id(
    batch_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BatchResponse:
    batch = await svc_get_batch_by_id(batch_id, session=session, user=user)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Batch not found"
        )
    return BatchResponse.model_validate(batch)
