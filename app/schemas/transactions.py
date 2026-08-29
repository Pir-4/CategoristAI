from decimal import Decimal
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core import (
    TransactionStatus,
    TransactionType,
)


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    account_id: UUID
    start_date: datetime
    completed_date: datetime
    amount: Decimal
    merchant: str | None
    category_id: UUID | None
    status: TransactionStatus
    transaction_type: TransactionType
    created_at: datetime


class TransactionUpdate(BaseModel):
    category_id: UUID | None = None
    status: TransactionStatus | None = None
    merchant: str | None = None
