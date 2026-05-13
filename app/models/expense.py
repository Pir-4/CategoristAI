from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core import BatchStatus, TransactionStatus

from .base import BaseModel


class Batch(BaseModel):
    __tablename__ = "batches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    upload_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    total_count: Mapped[int] = mapped_column(default=0)
    status: Mapped[BatchStatus] = mapped_column(
        String(20), default=BatchStatus.PROCESSING
    )


class Category(BaseModel):
    __tablename__ = "categories"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(30))
    description: Mapped[str | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(default=True)


class Expense(BaseModel):
    __tablename__ = "expenses"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("batches.id"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    description: Mapped[str] = mapped_column(String(50))
    merchant: Mapped[str | None] = mapped_column(String(50))
    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    status: Mapped[TransactionStatus] = mapped_column(
        String(20), default=TransactionStatus.PENDING
    )
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
