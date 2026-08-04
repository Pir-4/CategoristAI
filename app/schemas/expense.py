from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.core import BatchStatus, TransactionStatus


class CategoryBase(BaseModel):
    name: str = Field(min_length=1, max_length=30, title="Category name")
    description: str | None = Field(
        default=None, min_length=5, title="Category description"
    )


class CategoryCreate(CategoryBase): ...


class CategoryUpdate(BaseModel):
    name: str | None = Field(
        default=None, min_length=1, max_length=30, title="Category name"
    )
    description: str | None = Field(
        default=None, min_length=5, title="Category description"
    )
    is_active: bool | None = None


class CategoryRead(CategoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(title="Category ID", description="UUID v4")
    user_id: UUID = Field(title="User ID", description="UUID v4")
    is_active: bool
    created_at: datetime


class BatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(title="Batch ID", description="UUID v4")
    upload_at: datetime
    total_count: int
    status: BatchStatus


class ExpenseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(title="Expense ID", description="UUID v4")
    batch_id: UUID = Field(title="Batch ID", description="UUID v4")
    date: datetime
    amount: Decimal
    description: str
    merchant: str | None = None
    category: CategoryRead | None = None
    status: TransactionStatus
    created_at: datetime

    @field_serializer("amount")
    def serialize_amount(self, value: Decimal) -> str:
        return str(value)
