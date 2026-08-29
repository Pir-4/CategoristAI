from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.core import ErrorCode, SkipReason

from .transactions import TransactionResponse


class UploadIssue(BaseModel):
    """One row that was not imported, and why."""

    row_number: int | None = None
    line_number: int | None = None
    code: ErrorCode | SkipReason
    message: str
    field_name: str | None = None
    row: dict[str, str | None] | None = None
    details: dict[str, Any] | None = None


class UploadCounters(BaseModel):
    total_rows: int = 0
    parsed: int = 0
    saved: int = 0
    duplicates: int = 0
    skipped: int = 0
    failed: int = 0


class UploadResult(BaseModel):
    """Result of one CSV upload.

    `transactions` holds only the rows newly written to the database, so its
    length equals `counters.saved`, not `counters.total_rows`.
    """

    upload_id: str
    account_id: UUID
    counters: UploadCounters
    has_internal_errors: bool = False
    issues_truncated: bool = False
    transactions: list[TransactionResponse] = Field(default_factory=list)
    duplicates: list[UploadIssue] = Field(default_factory=list)
    skipped: list[UploadIssue] = Field(default_factory=list)
    failed: list[UploadIssue] = Field(default_factory=list)
