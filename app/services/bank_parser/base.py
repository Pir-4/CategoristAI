from abc import ABC, abstractmethod

from app.models import Expense


class BankParserBase(ABC):
    @abstractmethod
    def parse(self, raw_transactions: list[dict]) -> list[Expense]: ...
