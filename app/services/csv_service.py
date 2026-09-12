import io
import time
from collections import defaultdict
from csv import DictReader

import structlog
from fastapi import UploadFile

from app.core import elapsed_ms, settings
from app.core.exceptions import (
    CsvDecodeError,
    DuplicateHeadersError,
    EmptyCsvFileError,
    FileTooLargeError,
)
from app.models import Account, Transaction
from app.services.institution_parser import (
    CsvRow,
    ParsedCsv,
    ParseOutcome,
    get_parser,
)

logger = structlog.get_logger(__name__)


def identity_key(transaction: Transaction) -> tuple:
    """The columns that decide whether two rows are the same transaction.

    Mirrors the unique constraint on Transaction; `occurrence` is appended by
    the caller once it knows how many identical rows came before.
    """
    return (
        transaction.account_id,
        transaction.start_date,
        transaction.merchant,
        transaction.amount,
        transaction.fee,
    )


async def read_csv(file: UploadFile) -> ParsedCsv:
    """Read the upload into rows that still know their position in the file."""
    contents = await file.read()
    if len(contents) > settings.upload.max_bytes:
        raise FileTooLargeError(
            filename=file.filename,
            size_bytes=len(contents),
            max_bytes=settings.upload.max_bytes,
        )
    if not contents:
        raise EmptyCsvFileError(filename=file.filename)

    try:
        # utf-8-sig transparently strips a BOM if the bank ever adds one.
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as ex:
        raise CsvDecodeError(filename=file.filename, position=ex.start) from ex

    reader = DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise EmptyCsvFileError(filename=file.filename)

    header = list(reader.fieldnames)
    if len(set(header)) != len(header):
        # DictReader silently keeps only the last of duplicate columns.
        raise DuplicateHeadersError(headers=header)

    # reader.line_num is read after the record is yielded, so it points at the
    # last physical line of that record - correct even with quoted newlines.
    rows = [
        CsvRow(number=number, line=reader.line_num, data=data)
        for number, data in enumerate(reader, start=1)
    ]
    if not rows:
        raise EmptyCsvFileError(filename=file.filename)

    logger.info(
        "csv.read.done",
        filename=file.filename,
        bytes=len(contents),
        total_rows=len(rows),
        header=header,
    )
    return ParsedCsv(header=header, rows=rows)


async def parse_transactions(
    file: UploadFile, current_account: Account, accounts: list[Account]
) -> tuple[ParseOutcome, int]:
    """Parse the upload and number identical-looking rows within the file.

    Returns the outcome and the total number of data rows in the file.
    """
    started = time.perf_counter()
    parsed_csv = await read_csv(file)

    parser = get_parser(current_account.institution, accounts)
    parser.prepare(parsed_csv.header)

    outcome = parser.parse(parsed_csv.rows)

    # File order is stable, so the same file always produces the same
    # occurrence numbers — which is what keeps re-upload idempotent.
    seen: dict[tuple, int] = defaultdict(int)
    for item in outcome.parsed:
        transaction = item.transaction
        transaction.account_id = current_account.id
        key = identity_key(transaction)
        transaction.occurrence = seen[key]
        seen[key] += 1
        if transaction.occurrence:
            logger.debug(
                "csv.row.repeated",
                row_number=item.row.number,
                occurrence=transaction.occurrence,
            )

    total_rows = len(parsed_csv.rows)
    log_event = logger.warning if outcome.failed else logger.info
    log_event(
        "csv.parse.done",
        total_rows=total_rows,
        parsed=len(outcome.parsed),
        skipped=len(outcome.skipped),
        failed=len(outcome.failed),
        duration_ms=elapsed_ms(started),
    )
    return outcome, total_rows
