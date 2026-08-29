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
    JSON,
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
    """A single imported transaction.

    Identity — what counts as "the same transaction" — is expressed by the
    unique constraint below rather than by a hash computed in Python. Two rows
    clash only when every one of those columns is literally equal, so there is
    no digest to keep in sync and no chance of a collision silently dropping a
    real transaction. Changing the rule means changing the constraint, which
    Alembic detects and turns into a migration.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "start_date",
            "merchant",
            "amount",
            "fee",
            "occurrence",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))

    occurrence: Mapped[int] = mapped_column(default=0)
    """How many identical-looking rows preceded this one in the same file.

    Bank exports carry no time of day for some products, so a statement can
    legitimately contain the same date/merchant/amount twice. This counter is
    what keeps those two rows distinct while staying stable on re-upload,
    because file order is stable.
    """

    # Naive on purpose: a bank statement carries wall-clock local time with no
    # zone. Storing it in a tz-aware column would make Postgres attach the
    # session timezone on write and hand back a different value on read, which
    # breaks equality against the value the parser produced.
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    completed_date: Mapped[datetime] = mapped_column(DateTime(timezone=False))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
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
    raw_data: Mapped[dict] = mapped_column(JSON)
