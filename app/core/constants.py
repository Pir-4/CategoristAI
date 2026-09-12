from enum import StrEnum, auto


class AppMode(StrEnum):
    DEV = "development"
    PROD = "production"


class LogFormat(StrEnum):
    CONSOLE = auto()
    JSON = auto()


class ErrorCode(StrEnum):
    """Stable machine-readable ids returned to the client and logged."""

    # --- file level: nothing can be imported ---
    UNSUPPORTED_INSTITUTION = auto()
    EMPTY_CSV_FILE = auto()
    CSV_DECODE_FAILED = auto()
    CSV_FORMAT_UNKNOWN = auto()
    CSV_DUPLICATE_HEADERS = auto()
    FILE_TOO_LARGE = auto()

    # --- row level: one row is bad, import continues ---
    ROW_VALIDATION_FAILED = auto()
    ROW_MISSING_COLUMN = auto()
    ROW_UNKNOWN_STATE = auto()
    ROW_UNKNOWN_TRANSACTION_TYPE = auto()
    ROW_UNKNOWN_SAVING_OPERATION = auto()
    ROW_SAVING_AMOUNT_MISSING = auto()
    ROW_DESCRIPTION_RULE_MISSING = auto()
    ROW_INTERNAL_ERROR = auto()

    # --- persistence ---
    DUPLICATE_TRANSACTION = auto()
    TRANSACTION_PERSIST_FAILED = auto()
    DUPLICATE_IDENTITY_IN_BATCH = auto()

    # --- accounts ---
    ACCOUNT_NOT_FOUND = auto()
    ACCOUNT_NAME_ALREADY_TAKEN = auto()

    # --- transactions ---
    TRANSACTION_NOT_FOUND = auto()
    TRANSACTION_CATEGORY_NOT_FOUND = auto()

    # --- authentication / authorisation ---
    INVALID_CREDENTIALS = auto()
    INVALID_TOKEN = auto()
    TOKEN_EXPIRED = auto()
    REFRESH_TOKEN_INVALID = auto()
    PERMISSION_DENIED = auto()

    # --- users ---
    USER_NOT_FOUND = auto()
    LOGIN_ALREADY_TAKEN = auto()

    # --- generic ---
    HTTP_ERROR = auto()
    REQUEST_VALIDATION_FAILED = auto()

    # --- bugs ---
    INTERNAL_ERROR = auto()


class SkipReason(StrEnum):
    """Deliberate, expected reasons to leave a row out of the import.

    Kept separate from ErrorCode on purpose: a skip is not an error, and
    a closed enum makes "I don't know what this is" impossible to express
    as a skip.
    """

    PENDING_REFUND = auto()


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
    INTEREST = auto()
    INTERNAL_TRANSFER = auto()
    EXTERNAL_TRANSFER = auto()
