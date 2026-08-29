from abc import ABC, abstractmethod
from typing import Any

import structlog
from pydantic import ValidationError

from app.core import ErrorCode, SkipReason, settings
from app.core.exceptions import RowError
from app.models import Account, Transaction
from app.schemas.upload import UploadIssue

from .rows import CsvRow, ParsedTransaction, ParseOutcome

logger = structlog.get_logger(__name__)


def _issue(
    row: CsvRow,
    code: ErrorCode | SkipReason,
    message: str,
    field_name: str | None = None,
    details: dict[str, Any] | None = None,
) -> UploadIssue:
    return UploadIssue(
        row_number=row.number,
        line_number=row.line,
        code=code,
        message=message,
        field_name=field_name,
        row=row.data,
        details=details,
    )


def format_validation_error(exc: ValidationError) -> tuple[str, str | None]:
    """Collapse a multi-line pydantic error into one readable sentence."""
    parts: list[str] = []
    first_field: str | None = None
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "row"
        if first_field is None:
            first_field = location
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts), first_field


class InstitutionParserBase(ABC):
    def __init__(self, accounts: list[Account]):
        self.accounts = accounts
        self.row_model: Any = None

    def parse(self, rows: list[CsvRow]) -> ParseOutcome:
        """Parse every row. A single bad row never aborts the import."""
        outcome = ParseOutcome()
        max_logged = settings.upload.max_logged_failures

        for row in rows:
            log = logger.bind(row_number=row.number, line_number=row.line)
            try:
                reason = self.check_to_skip_tr(row)
                if reason is not None:
                    log.debug(
                        "csv.row.skipped", reason=str(reason), row=row.data
                    )
                    outcome.skipped.append(
                        _issue(row, reason, f"Row skipped: {reason}")
                    )
                    continue

                transaction = self.parse_row(row)
                outcome.parsed.append(ParsedTransaction(row, transaction))
                log.debug(
                    "csv.row.parsed",
                    merchant=transaction.merchant,
                    amount=str(transaction.amount),
                    transaction_type=str(transaction.transaction_type),
                )

            except RowError as ex:
                # Tier 1: a described data problem. No traceback needed.
                if len(outcome.failed) < max_logged:
                    log.warning(
                        "csv.row.failed", row=row.data, **ex.log_fields()
                    )
                outcome.failed.append(
                    _issue(row, ex.code, ex.message, details=ex.context)
                )

            except ValidationError as ex:
                # Tier 2: pydantic rejected the row - bad data, not a bug.
                message, field_name = format_validation_error(ex)
                if len(outcome.failed) < max_logged:
                    log.warning(
                        "csv.row.failed",
                        row=row.data,
                        error_code=str(ErrorCode.ROW_VALIDATION_FAILED),
                        reason=message,
                    )
                outcome.failed.append(
                    _issue(
                        row,
                        ErrorCode.ROW_VALIDATION_FAILED,
                        message,
                        field_name=field_name,
                    )
                )

            except Exception:
                # Tier 3: OUR BUG. Keep the traceback, keep importing, and
                # never let the stacktrace reach the client.
                log.exception("csv.row.crashed", row=row.data)
                outcome.failed.append(
                    _issue(
                        row,
                        ErrorCode.ROW_INTERNAL_ERROR,
                        "Internal error while processing this row",
                    )
                )

        return outcome

    def prepare(self, header: list[str]) -> None:
        """Decide the row format once for the whole file."""
        self.row_model = self.detect_format(header)

    @abstractmethod
    def detect_format(self, header: list[str]) -> Any:
        """Pick the row model for this file or raise UnknownCsvFormatError."""

    @abstractmethod
    def parse_row(self, row: CsvRow) -> Transaction: ...

    @abstractmethod
    def check_to_skip_tr(self, row: CsvRow) -> SkipReason | None: ...
