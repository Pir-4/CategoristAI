from enum import StrEnum


class AppMode(StrEnum):
    DEV = "development"
    PROD = "production"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"


class BatchStatus(StrEnum):
    PROCESSING = "processing"
    DONE = "done"


class ExpenseStatus(StrEnum):
    PENDING = "pending"
    CATEGORIZED = "categorized"
    REVIEWED = "reviewed"
