from abc import ABC, abstractmethod
import structlog

from app.core import TransactionType
from app.models import Transaction, Account
from typing import Generic, TypeVar

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class InstitutionParserBase(ABC, Generic[T]):
    def __init__(self, accounts: list[Account]):
        self.accounts = accounts

    def parse(self, raw_transactions: list[dict]) -> list[Transaction]:
        return [self.parse_row(tr) for tr in raw_transactions]

    @abstractmethod
    def parse_row(self, row: dict) -> Transaction: ...

    @abstractmethod
    def get_transaction_type(self, inter_transaction: T) -> TransactionType: ...
