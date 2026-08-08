import structlog
import re

from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from app.core import (
    TransactionType,
)
from app.models import Transaction
from .base import InstitutionParserBase

logger = structlog.get_logger(__name__)


class RevolutRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    transaction_type: str = Field(alias="Type")
    start_date: datetime = Field(alias="Started Date")
    completed_date: datetime = Field(alias="Completed Date")
    description: str = Field(alias="Description")
    amount: Decimal = Field(alias="Amount")
    fee: Decimal = Field(alias="Fee")
    currency: str = Field(alias="Currency")
    state: str = Field(alias="State")
    balance: Decimal = Field(alias="Balance")
    product: str = Field(alias="Product")


class RevolutParser(InstitutionParserBase[RevolutRow]):
    def parse_row(self, row: dict) -> Transaction:
        return self.map_to_transaction(RevolutRow(**row))

    def map_to_transaction(self, tr: RevolutRow) -> Transaction:
        transaction_type = self.get_transaction_type(tr)
        description = self.edit_description(transaction_type, tr.description)
        return Transaction(
            start_date=tr.start_date,
            completed_date=tr.completed_date,
            amount=abs(tr.amount),
            transaction_type=transaction_type,
            description=description,
        )

    def get_transaction_type(self, in_tr: RevolutRow) -> TransactionType:
        if in_tr.transaction_type == "Card Payment":
            return TransactionType.EXPENSE
        if in_tr.transaction_type == "Exchange":
            return TransactionType.INCOME
        if in_tr.transaction_type == "Transfer":
            if any(
                account.institution_acc_name in in_tr.description
                for account in self.accounts
            ):
                return TransactionType.INTERNAL_TRANSFER
            return TransactionType.EXTERNAL_TRANSFER

        raise ValueError(f"Unknown type {in_tr}")

    @staticmethod
    def edit_description(tr_type: TransactionType, description: str):
        if tr_type in [TransactionType.INCOME, TransactionType.EXPENSE]:
            return description

        if tr_type in [
            TransactionType.INTERNAL_TRANSFER,
            TransactionType.EXTERNAL_TRANSFER,
        ]:
            return re.sub(r"^(Transfer\s+)?(To|From)\s+", "", description)

        raise ValueError(f"Unknown type {tr_type} for descriptor {description}")
