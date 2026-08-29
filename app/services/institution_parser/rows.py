"""Transport objects that keep the link "CSV row -> Transaction" alive.

Without these the line number dies inside parse_csv and the user can never be
told which row of their file went wrong.
"""

from dataclasses import dataclass, field

from app.core import ErrorCode
from app.models import Transaction
from app.schemas.upload import UploadIssue


@dataclass(frozen=True, slots=True)
class CsvRow:
    number: int
    """1-based index among data rows - what the user counts."""

    line: int
    """Physical line in the file - differs from `number` as soon as a quoted
    field contains a newline. This is what you use when opening the file."""

    data: dict[str, str | None]


@dataclass(frozen=True, slots=True)
class ParsedCsv:
    header: list[str]
    rows: list[CsvRow]


@dataclass(slots=True)
class ParsedTransaction:
    row: CsvRow
    transaction: Transaction


@dataclass(slots=True)
class ParseOutcome:
    parsed: list[ParsedTransaction] = field(default_factory=list)
    skipped: list[UploadIssue] = field(default_factory=list)
    failed: list[UploadIssue] = field(default_factory=list)

    @property
    def has_internal_errors(self) -> bool:
        return any(
            issue.code == ErrorCode.ROW_INTERNAL_ERROR for issue in self.failed
        )
