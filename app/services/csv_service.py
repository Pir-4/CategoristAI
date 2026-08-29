import hashlib
import io
import time
from collections import defaultdict
from csv import DictReader

import structlog
from fastapi import UploadFile

from app.core import settings
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


def get_tr_hash_data(transaction: Transaction) -> str:
    return (
        str(transaction.account_id)
        + str(transaction.start_date.isoformat())
        + str(transaction.merchant)
        + str(transaction.amount)
        + str(transaction.fee)
    )


def build_dedup_hash(transaction: Transaction, occurrence: int) -> str:
    data = get_tr_hash_data(transaction) + str(occurrence)
    return hashlib.sha256(data.encode()).hexdigest()


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
    """Parse the upload and assign a dedup hash to every parsed transaction.

    Returns the outcome and the total number of data rows in the file.
    """
    started = time.perf_counter()
    parsed_csv = await read_csv(file)

    parser = get_parser(current_account.institution, accounts)
    parser.prepare(parsed_csv.header)

    outcome = parser.parse(parsed_csv.rows)

    occurrence_counts: dict[str, int] = defaultdict(int)
    for item in outcome.parsed:
        transaction = item.transaction
        transaction.account_id = current_account.id
        key = get_tr_hash_data(transaction)
        occurrence = occurrence_counts[key]
        occurrence_counts[key] += 1
        transaction.dedup_hash = build_dedup_hash(
            transaction=transaction, occurrence=occurrence
        )
        logger.debug(
            "csv.row.hashed",
            row_number=item.row.number,
            dedup_hash=transaction.dedup_hash,
        )

    total_rows = len(parsed_csv.rows)
    log_event = logger.warning if outcome.failed else logger.info
    log_event(
        "csv.parse.done",
        total_rows=total_rows,
        parsed=len(outcome.parsed),
        skipped=len(outcome.skipped),
        failed=len(outcome.failed),
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
    )
    return outcome, total_rows
