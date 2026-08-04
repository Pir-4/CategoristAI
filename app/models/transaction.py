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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import (
    AccountType,
    BatchStatus,
    TransactionStatus,
    TransactionType,
)

from .base import BaseModel


class AccountKeyword(BaseModel):
    __tablename__ = "account_keywords"
    __table_args__ = (UniqueConstraint("account_id", "keyword"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    keyword: Mapped[str] = mapped_column(String(100))


class Account(BaseModel):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(30))
    account_type: Mapped[AccountType] = mapped_column(String(20))
    keywords: Mapped[list[AccountKeyword]] = relationship(
        "AccountKeyword", lazy="selectin"
    )
    initial_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    balance_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    is_balance_tracked: Mapped[bool] = mapped_column(default=True)
    is_categorizable: Mapped[bool] = mapped_column(default=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class Batch(BaseModel):
    __tablename__ = "batches"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
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


class Transaction(BaseModel):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("batches.id"))
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"))
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
    transaction_type: Mapped[TransactionType] = mapped_column(String(20))
    raw_type: Mapped[str] = mapped_column(String(30))
    dedup_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_categorizable: Mapped[bool] = mapped_column(default=True)


class BalanceSnapshot(BaseModel):
    __tablename__ = "balance_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("batches.id"))
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountInterest(BaseModel):
    __tablename__ = "account_interests"
    __table_args__ = (UniqueConstraint("account_id", "year", "month"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    year: Mapped[int]
    month: Mapped[int]
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
