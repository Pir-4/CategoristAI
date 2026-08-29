from abc import ABC, abstractmethod
import structlog

from app.core import TransactionType
from app.models import Transaction, Account
from typing import Generic, TypeVar

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class InstitutionParserBase(ABC, Generic[T]):
    errors: list[dict]
    transactions: list[Transaction]

    def __init__(self, accounts: list[Account]):
        self.accounts = accounts
        self.transactions = []
        self.errors = []

    def parse(self, raw_transactions: list[dict]) -> list[Transaction]:
        for tr in raw_transactions:
            try:
                if reason := self.check_to_skip_tr(tr):
                    self.errors.append({"error": str(reason), "row": tr})
                    continue

                self.transactions.append(self.parse_row(tr))
            except Exception as ex:
                self.errors.append({"error": str(ex), "row": tr})

        return self.transactions

    @abstractmethod
    def parse_row(self, row: dict) -> Transaction: ...

    @abstractmethod
    def get_transaction_type(self, inter_transaction: T) -> TransactionType: ...

    @abstractmethod
    def check_to_skip_tr(self, row: dict) -> str | None: ...
