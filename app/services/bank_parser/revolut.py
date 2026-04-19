from datetime import datetime
from decimal import Decimal

from app.models import Expense

from .base import BankParserBase


class RevolutParser(BankParserBase):
    def parse(self, raw_transactions: list[dict]) -> list[Expense]:
        result: list[Expense] = []
        for transaction in raw_transactions:
            if transaction["Type"] != "Card Payment":
                continue

            if transaction["State"] != "COMPLETED":
                continue

            expense = Expense(
                date=datetime.strptime(
                    transaction["Completed Date"], "%Y-%m-%d %H:%M:%S"
                ),
                amount=abs(Decimal(transaction["Amount"])),
                merchant=transaction["Description"],
                description=transaction["Description"],
            )
            result.append(expense)
        return result
