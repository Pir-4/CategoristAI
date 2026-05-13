from datetime import datetime
from decimal import Decimal

from app.models import Transaction

from .base import BankParserBase


class RevolutParser(BankParserBase):
    def parse(self, raw_transactions: list[dict]) -> list[Transaction]:
        result: list[Transaction] = []
        for transaction in raw_transactions:
            if transaction["Type"] != "Card Payment":
                continue

            if transaction["State"] != "COMPLETED":
                continue

            expense = Transaction(
                date=datetime.strptime(
                    transaction["Completed Date"], "%Y-%m-%d %H:%M:%S"
                ),
                amount=abs(Decimal(transaction["Amount"])),
                merchant=transaction["Description"],
                description=transaction["Description"],
            )
            result.append(expense)
        return result
