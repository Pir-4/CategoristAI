import logging
from abc import ABC, abstractmethod
from enum import Enum

from app.core.constants import AccountType, TransactionType
from app.models import Account, Transaction

logger = logging.getLogger(__name__)


class CategoryType(Enum):
    ALWAYS = 1
    NEVER = 0
    DEPENDS = -1


class BankParserBase(ABC):
    def __init__(self):
        self.account_transaction_type_map = {
            AccountType.SAVINGS: TransactionType.INTERNAL_TRANSFER,
            AccountType.JOINT: TransactionType.INTERNAL_TRANSFER,
            AccountType.INVESTMENT: TransactionType.EXTERNAL_TRANSFER,
            AccountType.PERSONAL: TransactionType.EXTERNAL_TRANSFER,
        }
        self.transaction_type_categorized_map = {
            TransactionType.EXPENSE: CategoryType.ALWAYS,
            TransactionType.INCOME: CategoryType.NEVER,
            TransactionType.INTERNAL_TRANSFER: CategoryType.NEVER,
            TransactionType.EXTERNAL_TRANSFER: CategoryType.DEPENDS,
        }

    @abstractmethod
    def parse(
        self, raw_transactions: list[dict], accounts: list[Account]
    ) -> list[Transaction]: ...

    @staticmethod
    def get_account(accounts: list[Account], keyword: str) -> Account | None:
        sorted_accounts = sorted(
            accounts, key=lambda a: len(a.match_keyword), reverse=True
        )
        for account in sorted_accounts:
            if account.match_keyword.lower() in keyword.lower():
                return account
        logger.debug("parser.account.no_match", description=keyword)
        return None

    @abstractmethod
    def is_income(self, raw_transaction: dict) -> bool: ...

    def get_transaction_type(
        self, account: Account | None, raw_transaction: dict
    ):
        if account is not None:
            result = self.account_transaction_type_map.get(account.account_type)
            if result:
                return result
        return (
            TransactionType.INCOME
            if self.is_income(raw_transaction)
            else TransactionType.EXPENSE
        )

    def is_categorizable(
        self, transaction_type: TransactionType, account: Account | None
    ) -> bool:
        category = self.transaction_type_categorized_map[transaction_type]
        if category != CategoryType.DEPENDS:
            return bool(category)

        return account.is_categorizable if account else False
