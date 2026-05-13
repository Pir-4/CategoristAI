import logging
from datetime import datetime
from decimal import Decimal

from app.core.constants import TransactionType
from app.models import Account, Transaction

from .base import BankParserBase

logger = logging.getLogger(__name__)


class RevolutParser(BankParserBase):
    def parse(
        self, raw_transactions: list[dict], accounts: list[Account]
    ) -> list[Transaction]:
        result: list[Transaction] = []
        for raw_transaction in raw_transactions:
            description = raw_transaction["Description"]
            if raw_transaction["State"] != "COMPLETED":
                logger.debug(
                    "revolut.skip.state",
                    description=description,
                    state=raw_transaction["State"],
                )

                continue

            raw_type = raw_transaction["Type"]
            account = self.get_account(accounts, description)
            transaction_type = self.get_transaction_type(
                account, raw_transaction
            )
            is_categorizable = self.is_categorizable(transaction_type, account)
            merchant = (
                description
                if transaction_type == TransactionType.EXPENSE
                else None
            )

            logger.debug(
                "revolut.classify",
                description=description,
                transaction_type=transaction_type,
                account=account.name if account else None,
            )

            transaction = Transaction(
                date=datetime.strptime(
                    raw_transaction["Completed Date"], "%Y-%m-%d %H:%M:%S"
                ),
                amount=Decimal(raw_transaction["Amount"]),
                merchant=merchant,
                description=description,
                transaction_type=transaction_type,
                raw_type=raw_type,
                account_id=account.id if account else None,
                is_categorizable=is_categorizable,
            )
            result.append(transaction)
        return result

    def is_income(self, raw_transaction: dict) -> bool:
        amount = Decimal(raw_transaction["Amount"])
        return amount > 0
