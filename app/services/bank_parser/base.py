from abc import ABC, abstractmethod

from app.models import Transaction


class BankParserBase(ABC):
    @abstractmethod
    def parse(self, raw_transactions: list[dict]) -> list[Transaction]: ...
