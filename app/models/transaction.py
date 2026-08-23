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

from app.core import (
    Institution,
    TransactionStatus,
    TransactionType,
)

from .base import BaseModel


class Account(BaseModel):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(30))
    institution_acc_name: Mapped[str] = mapped_column(String(100))
    institution: Mapped[Institution] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(default=True)


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


class Transaction(BaseModel):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)

    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    merchant: Mapped[str] = mapped_column(String(150))
    transaction_type: Mapped[TransactionType] = mapped_column(String(20))

    category_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("categories.id")
    )
    status: Mapped[TransactionStatus] = mapped_column(
        String(20), default=TransactionStatus.PENDING
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
