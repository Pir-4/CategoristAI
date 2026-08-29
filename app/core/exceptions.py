"""Domain exceptions.

Three planes, kept apart on purpose:

* ``UploadError``   - file level. Nothing can be imported, abort the request.
* ``RowError``      - row level. Collected, never aborts the import.
* ``InvariantError`` - "this cannot happen". A bug, fail loud with a 500.

Every class carries a stable ``code`` so two errors with similar wording are
still distinguishable in logs and in the API response.
"""

from typing import Any

from .constants import ErrorCode


class AppError(Exception):
    """Root of every error CategoristAI raises deliberately."""

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    http_status: int = 500
    message: str = "Unexpected application error"

    def __init__(self, message: str | None = None, **context: Any):
        self.message = message or type(self).message
        self.context = context
        super().__init__(self.message)

    def __str__(self) -> str:
        base = f"[{self.code}] {self.message}"
        if not self.context:
            return base
        details = ", ".join(f"{k}={v!r}" for k, v in self.context.items())
        return f"{base} ({details})"

    def log_fields(self) -> dict[str, Any]:
        """Structured fields for structlog - never a pre-formatted string."""
        return {"error_code": str(self.code), **self.context}


class UploadError(AppError):
    """File level: the upload cannot proceed at all."""

    http_status = 422


class RowError(AppError):
    """Row level: this row is bad, the rest of the file is still fine."""

    http_status = 422


class InvariantError(AppError):
    """A guarantee the code makes was violated. This is a bug."""

    code = ErrorCode.INTERNAL_ERROR
    http_status = 500


# --------------------------------------------------------------------------
# File level
# --------------------------------------------------------------------------


class AccountNotFoundError(UploadError):
    code = ErrorCode.ACCOUNT_NOT_FOUND
    http_status = 404
    message = "Account not found"


class UnsupportedInstitutionError(UploadError):
    code = ErrorCode.UNSUPPORTED_INSTITUTION
    message = "No CSV parser is available for this institution"


class EmptyCsvFileError(UploadError):
    code = ErrorCode.EMPTY_CSV_FILE
    http_status = 400
    message = "The uploaded file is empty or has no data rows"


class CsvDecodeError(UploadError):
    code = ErrorCode.CSV_DECODE_FAILED
    http_status = 400
    message = "The uploaded file is not valid UTF-8 text"


class UnknownCsvFormatError(UploadError):
    code = ErrorCode.CSV_FORMAT_UNKNOWN
    message = "CSV header does not match any known export format"


class DuplicateHeadersError(UploadError):
    code = ErrorCode.CSV_DUPLICATE_HEADERS
    message = "CSV header contains duplicate column names"


class FileTooLargeError(UploadError):
    code = ErrorCode.FILE_TOO_LARGE
    http_status = 413
    message = "The uploaded file is too large"


# --------------------------------------------------------------------------
# Row level
# --------------------------------------------------------------------------


class RowValidationError(RowError):
    code = ErrorCode.ROW_VALIDATION_FAILED
    message = "Row does not match the expected format"


class MissingColumnError(RowError):
    code = ErrorCode.ROW_MISSING_COLUMN
    message = "Required column is missing from this row"


class UnknownRowStateError(RowError):
    code = ErrorCode.ROW_UNKNOWN_STATE
    message = "Unrecognised transaction state"


class UnknownTransactionTypeError(RowError):
    code = ErrorCode.ROW_UNKNOWN_TRANSACTION_TYPE
    message = "Cannot derive a transaction type for this row"


class UnknownSavingOperationError(RowError):
    code = ErrorCode.ROW_UNKNOWN_SAVING_OPERATION
    message = "Unknown savings operation in the Description column"


class SavingAmountMissingError(RowError):
    code = ErrorCode.ROW_SAVING_AMOUNT_MISSING
    message = "Savings row has no amount in Money in / Money out"


class DescriptionRuleMissingError(RowError):
    code = ErrorCode.ROW_DESCRIPTION_RULE_MISSING
    message = "No description cleanup rule for this transaction type"


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class TransactionPersistError(AppError):
    code = ErrorCode.TRANSACTION_PERSIST_FAILED
    http_status = 500
    message = "Failed to save transactions"


class DedupHashCollisionError(InvariantError):
    code = ErrorCode.DEDUP_HASH_COLLISION
    message = "Two transactions in one batch share a dedup hash"


class UnexpectedRowModelError(InvariantError):
    message = "Parsed row model has no mapping to a Transaction"
