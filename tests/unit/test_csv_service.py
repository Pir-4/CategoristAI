"""CSV reading: rejecting broken files and keeping track of row positions."""

import io

import pytest
from fastapi import UploadFile

from app.core import settings
from app.core.exceptions import (
    AppError,
    CsvDecodeError,
    DuplicateHeadersError,
    EmptyCsvFileError,
    FileTooLargeError,
)
from app.services.csv_service import read_csv

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _upload(content: bytes, filename: str = "statement.csv") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.parametrize(
    ("content", "expected", "status"),
    [
        pytest.param(b"", EmptyCsvFileError, 400, id="empty_file"),
        pytest.param(
            b"Type,Product\n", EmptyCsvFileError, 400, id="header_without_rows"
        ),
        pytest.param(
            b"Type,Type\n1,2\n",
            DuplicateHeadersError,
            422,
            id="duplicate_header",
        ),
        pytest.param(
            "Тип,Дата\nа,б\n".encode("cp1251"),
            CsvDecodeError,
            400,
            id="not_utf8",
        ),
    ],
)
async def test_read_csv_rejects_bad_file(
    content: bytes, expected: type[AppError], status: int
):
    with pytest.raises(expected) as excinfo:
        await read_csv(_upload(content))

    # A broken upload is the caller's problem, never a 500.
    assert excinfo.value.http_status == status
    assert excinfo.value.code


async def test_read_csv_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr(settings.upload, "max_bytes", 10)

    with pytest.raises(FileTooLargeError) as excinfo:
        await read_csv(_upload(b"Type,Product\n" + b"x" * 100))

    assert excinfo.value.http_status == 413


async def test_row_numbers_survive_quoted_newline():
    """`number` counts data rows, `line` counts physical lines.

    They diverge as soon as a quoted field contains a newline, which is why
    DictReader.line_num is used instead of enumerate() — a caller reading
    "row 2" in the report must be able to find it in a text editor.
    """
    content = (
        b"Date,Description\n"
        b'1 Jul 2025,"first\nstill first"\n'
        b"2 Jul 2025,second\n"
    )

    parsed = await read_csv(_upload(content))

    assert [row.number for row in parsed.rows] == [1, 2]
    assert [row.line for row in parsed.rows] == [3, 4]
    assert parsed.rows[0].data["Description"] == "first\nstill first"


async def test_read_csv_strips_bom_if_present():
    """utf-8-sig keeps a BOM out of the first header name."""
    content = "Date,Description\n1 Jul 2025,x\n".encode("utf-8-sig")

    parsed = await read_csv(_upload(content))

    assert parsed.header == ["Date", "Description"]
