import structlog
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from decimal import Decimal
from app.core import (
    TransactionType,
)
from app.models import Transaction
from .base import InstitutionParserBase

logger = structlog.get_logger(__name__)


class RevolutRow(BaseModel):
    @classmethod
    def matches(cls, row: dict) -> bool:
        aliases = {f.alias for f in cls.model_fields.values() if f.alias}
        return aliases.issubset(row.keys())


class RevolutAccountRow(RevolutRow):
    model_config = ConfigDict(populate_by_name=True)

    transaction_type: str = Field(alias="Type")
    start_date: datetime = Field(alias="Started Date")
    completed_date: datetime | None = Field(alias="Completed Date")
    description: str = Field(alias="Description")
    amount: Decimal = Field(alias="Amount")
    fee: Decimal = Field(alias="Fee")
    currency: str = Field(alias="Currency")
    state: str = Field(alias="State")
    balance: Decimal | None = Field(alias="Balance")
    product: str = Field(alias="Product")

    @field_validator("start_date", "completed_date", mode="before")
    @classmethod
    def pad_single_digit_hour(cls, v):
        # Completed Date is blank for rows that never completed (e.g. REVERTED)
        if not v:
            return None
        # Revolut export sometimes omits the leading zero on the hour,
        # e.g. "2026-04-28 7:48:25" instead of "2026-04-28 07:48:25"
        pattern = r"^(\d{4}-\d{2}-\d{2}) (\d):(\d{2}:\d{2})$"
        return re.sub(pattern, r"\1 0\2:\3", v)

    @field_validator("balance", mode="before")
    @classmethod
    def empty_balance_to_none(cls, v):
        # Balance is blank for rows that never completed (e.g. REVERTED)
        return v or None


class RevolutSavingRow(RevolutRow):
    model_config = ConfigDict(populate_by_name=True)

    date: datetime = Field(alias="Date")
    description: str = Field(alias="Description")
    money_out: Decimal | None = Field(alias="Money out")
    money_in: Decimal | None = Field(alias="Money in")
    balance: Decimal = Field(alias="Balance")

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, v):
        # Revolut export sometimes spells September as "Sept" instead of "Sep"
        v = re.sub(r"\bSept\b", "Sep", v)
        return datetime.strptime(v, "%d %b %Y")

    @field_validator("money_in", "money_out", mode="before")
    @classmethod
    def clean_amount(cls, v):
        if not v:
            return None
        cleaned = re.sub(r"[^\d.]", "", v)  # оставляем только цифры и точку
        return Decimal(cleaned) if cleaned else None

    @field_validator("balance", mode="before")
    @classmethod
    def clean_balance(cls, v):
        return re.sub(r"[^\d.]", "", v)


class RevolutParser(InstitutionParserBase[RevolutRow]):
    def parse_row(self, row: dict) -> Transaction:
        for model in [RevolutAccountRow, RevolutSavingRow]:
            if model.matches(row):
                tr = self.map_to_transaction(model(**row))
                tr.raw_data = row
                return tr
        raise ValueError(f"Unknown CSV format, headers: {list(row.keys())}")

    def check_to_skip_tr(self, row: dict) -> str | None:
        state = row.get("State")
        if not state:
            return None
        if state in ("COMPLETED", "REVERTED"):
            return None
        if state == "PENDING":
            tr_type = row["Type"]
            if tr_type == "Card Payment":
                return None
            elif tr_type == "Card Refund":
                return "Refund in pending status"
        return "Unknown transaction to skip"

    def map_to_transaction(self, tr: RevolutRow) -> Transaction:
        if isinstance(tr, RevolutAccountRow):
            return self.map_account_to_transaction(tr)
        if isinstance(tr, RevolutSavingRow):
            return self.map_saving_acc_to_transaction(tr)

        raise ValueError(f"Unexpected transaction type {tr}")

    def map_account_to_transaction(self, tr: RevolutAccountRow) -> Transaction:
        transaction_type = self.get_transaction_type(tr)
        description = self.edit_description(transaction_type, tr.description)
        return Transaction(
            start_date=tr.start_date,
            completed_date=tr.completed_date or tr.start_date,
            amount=tr.amount,
            fee=tr.fee,
            transaction_type=transaction_type,
            merchant=description,
        )

    def map_saving_acc_to_transaction(
        self, tr: RevolutSavingRow
    ) -> Transaction:
        transaction_type = self.get_saving_transaction_type(tr)
        amount = self.get_amount_saving_transaction(tr)
        return Transaction(
            start_date=tr.date,
            completed_date=tr.date,
            amount=amount,
            transaction_type=transaction_type,
            merchant=tr.description,
        )

    def get_transaction_type(self, in_tr: RevolutAccountRow) -> TransactionType:
        if in_tr.transaction_type == "Transfer":
            if any(
                account.institution_acc_name in in_tr.description
                for account in self.accounts
            ):
                return TransactionType.INTERNAL_TRANSFER
            return TransactionType.EXTERNAL_TRANSFER
        elif in_tr.transaction_type in "Charge":
            return TransactionType.EXPENSE
        elif in_tr.amount > 0:
            return TransactionType.INCOME
        elif in_tr.amount < 0:
            return TransactionType.EXPENSE

        raise ValueError(f"Unknown type {in_tr}")

    @staticmethod
    def get_saving_transaction_type(in_tr: RevolutSavingRow) -> TransactionType:
        if in_tr.description == "Gross Interest":
            return TransactionType.INTEREST
        if in_tr.description in ("Withdrawal", "Deposit"):
            return TransactionType.INTERNAL_TRANSFER
        raise ValueError(f"Unknown type {in_tr}")

    @staticmethod
    def get_amount_saving_transaction(in_tr: RevolutSavingRow) -> Decimal:
        if in_tr.description in ("Gross Interest", "Deposit"):
            return in_tr.money_in
        if in_tr.description == "Withdrawal":
            return -1 * in_tr.money_out
        raise ValueError(f"Unknown type {in_tr}")

    @staticmethod
    def edit_description(tr_type: TransactionType, description: str):
        if tr_type == TransactionType.EXPENSE:
            return description

        if tr_type in [TransactionType.INCOME]:
            return re.sub(
                r"^Payment\s+(From)\s+",
                "",
                description,
                flags=re.IGNORECASE,
            )

        if tr_type in [
            TransactionType.INTERNAL_TRANSFER,
            TransactionType.EXTERNAL_TRANSFER,
        ]:
            return re.sub(
                r"^(Transfer\s+)?(To|From)\s+",
                "",
                description,
                flags=re.IGNORECASE,
            )

        raise ValueError(f"Unknown type {tr_type} for descriptor {description}")
