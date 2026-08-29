import re
from datetime import datetime
from decimal import Decimal
from typing import ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import SkipReason, TransactionType
from app.core.exceptions import (
    DescriptionRuleMissingError,
    MissingColumnError,
    SavingAmountMissingError,
    UnexpectedRowModelError,
    UnknownCsvFormatError,
    UnknownRowStateError,
    UnknownSavingOperationError,
    UnknownTransactionTypeError,
)
from app.models import Transaction

from .base import InstitutionParserBase
from .rows import CsvRow

logger = structlog.get_logger(__name__)

MERCHANT_MAX_LENGTH = 150

COMPLETED_STATES = ("COMPLETED", "REVERTED")
# Card payments already move the balance while pending - they must be counted.
PENDING_ALLOWED_TYPES = ("Card Payment",)


class RevolutRow(BaseModel):
    @classmethod
    def matches(cls, header: list[str]) -> bool:
        aliases = {f.alias for f in cls.model_fields.values() if f.alias}
        return aliases.issubset(set(header))


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
        cleaned = re.sub(r"[^\d.]", "", v)  # digits and dot only
        return Decimal(cleaned) if cleaned else None

    @field_validator("balance", mode="before")
    @classmethod
    def clean_balance(cls, v):
        return re.sub(r"[^\d.]", "", v)


class RevolutParser(InstitutionParserBase):
    ROW_MODELS: ClassVar[tuple[type[RevolutRow], ...]] = (
        RevolutAccountRow,
        RevolutSavingRow,
    )

    def detect_format(self, header: list[str]) -> type[RevolutRow]:
        for model in self.ROW_MODELS:
            if model.matches(header):
                logger.debug("csv.format.detected", row_format=model.__name__)
                return model
        raise UnknownCsvFormatError(
            headers=header,
            known_formats=[m.__name__ for m in self.ROW_MODELS],
        )

    def parse_row(self, row: CsvRow) -> Transaction:
        transaction = self.map_to_transaction(self.row_model(**row.data))
        transaction.raw_data = row.data
        return transaction

    def check_to_skip_tr(self, row: CsvRow) -> SkipReason | None:
        if self.row_model is not RevolutAccountRow:
            # Savings exports have no State column at all.
            return None

        state = row.data.get("State")
        if not state or state in COMPLETED_STATES:
            return None

        if state == "PENDING":
            tr_type = row.data.get("Type")
            if tr_type is None:
                raise MissingColumnError(column="Type")
            if tr_type in PENDING_ALLOWED_TYPES:
                return None
            if tr_type == "Card Refund":
                return SkipReason.PENDING_REFUND

        raise UnknownRowStateError(state=state, row_type=row.data.get("Type"))

    def map_to_transaction(self, tr: RevolutRow) -> Transaction:
        if isinstance(tr, RevolutAccountRow):
            return self.map_account_to_transaction(tr)
        if isinstance(tr, RevolutSavingRow):
            return self.map_saving_acc_to_transaction(tr)

        raise UnexpectedRowModelError(model=type(tr).__name__)

    def map_account_to_transaction(self, tr: RevolutAccountRow) -> Transaction:
        transaction_type = self.get_transaction_type(tr)
        description = self.edit_description(transaction_type, tr.description)
        return Transaction(
            start_date=tr.start_date,
            completed_date=tr.completed_date or tr.start_date,
            amount=tr.amount,
            fee=tr.fee,
            transaction_type=transaction_type,
            merchant=description[:MERCHANT_MAX_LENGTH],
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
            # Explicit: the column default only applies at INSERT, so leaving
            # this None would put the string "None" into the dedup hash.
            fee=Decimal(0),
            transaction_type=transaction_type,
            merchant=tr.description[:MERCHANT_MAX_LENGTH],
        )

    def get_transaction_type(self, in_tr: RevolutAccountRow) -> TransactionType:
        if in_tr.transaction_type == "Transfer":
            if any(
                account.institution_acc_name in in_tr.description
                for account in self.accounts
            ):
                return TransactionType.INTERNAL_TRANSFER
            return TransactionType.EXTERNAL_TRANSFER
        if in_tr.transaction_type == "Charge":
            return TransactionType.EXPENSE
        if in_tr.amount > 0:
            return TransactionType.INCOME
        if in_tr.amount < 0:
            return TransactionType.EXPENSE

        raise UnknownTransactionTypeError(
            raw_type=in_tr.transaction_type, amount=str(in_tr.amount)
        )

    @staticmethod
    def get_saving_transaction_type(
        in_tr: RevolutSavingRow,
    ) -> TransactionType:
        if in_tr.description == "Gross Interest":
            return TransactionType.INTEREST
        if in_tr.description in ("Withdrawal", "Deposit"):
            return TransactionType.INTERNAL_TRANSFER
        raise UnknownSavingOperationError(description=in_tr.description)

    @staticmethod
    def get_amount_saving_transaction(in_tr: RevolutSavingRow) -> Decimal:
        if in_tr.description in ("Gross Interest", "Deposit"):
            if in_tr.money_in is None:
                raise SavingAmountMissingError(
                    description=in_tr.description, column="Money in"
                )
            return in_tr.money_in
        if in_tr.description == "Withdrawal":
            if in_tr.money_out is None:
                raise SavingAmountMissingError(
                    description=in_tr.description, column="Money out"
                )
            return -1 * in_tr.money_out
        raise UnknownSavingOperationError(description=in_tr.description)

    @staticmethod
    def edit_description(tr_type: TransactionType, description: str) -> str:
        if tr_type == TransactionType.EXPENSE:
            return description

        if tr_type == TransactionType.INCOME:
            return re.sub(
                r"^Payment\s+(From)\s+",
                "",
                description,
                flags=re.IGNORECASE,
            )

        if tr_type in (
            TransactionType.INTERNAL_TRANSFER,
            TransactionType.EXTERNAL_TRANSFER,
        ):
            return re.sub(
                r"^(Transfer\s+)?(To|From)\s+",
                "",
                description,
                flags=re.IGNORECASE,
            )

        raise DescriptionRuleMissingError(
            transaction_type=str(tr_type), description=description
        )
