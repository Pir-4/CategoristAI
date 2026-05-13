from enum import StrEnum, auto


class AppMode(StrEnum):
    DEV = "development"
    PROD = "production"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class BatchStatus(StrEnum):
    PROCESSING = "processing"
    DONE = "done"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    CATEGORIZED = "categorized"
    REVIEWED = "reviewed"


class TransactionType(StrEnum):
    EXPENSE = auto()
    INCOME = auto()
    INTERNAL_TRANSFER = auto()
    EXTERNAL_TRANSFER = auto()


class AccountType(StrEnum):
    SAVINGS = auto()
    INVESTMENT = auto()
    PERSONAL = auto()
    JOINT = auto()
