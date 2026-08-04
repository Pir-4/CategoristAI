from enum import StrEnum, auto


class AppMode(StrEnum):
    DEV = "development"
    PROD = "production"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class Institution(StrEnum):
    REVOLUT = auto()


class TransactionStatus(StrEnum):
    PENDING = auto()
    CATEGORIZED = auto()
    REVIEWED = auto()


class TransactionType(StrEnum):
    EXPENSE = auto()
    INCOME = auto()
    INTERNAL_TRANSFER = auto()
    EXTERNAL_TRANSFER = auto()
