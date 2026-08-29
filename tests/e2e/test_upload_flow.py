"""End-to-end upload: real HTTP, real database, real parser.

Everything written here is rolled back with the surrounding transaction.
"""

import pytest
from httpx import AsyncClient

from tests.test_data.revolut_cases import (
    ACCOUNT_CASES,
    ACCOUNT_HEADER,
    REPEATED_SAVING_ROWS,
    SAVING_HEADER,
    UNKNOWN_HEADER,
    UNKNOWN_ROWS,
    cases_to_csv,
    counts,
    to_csv_bytes,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def _upload_file(content: bytes, name: str = "statement.csv"):
    return {"upload_file": (name, content, "text/csv")}


async def test_upload_reports_saved_skipped_and_duplicates(
    auth_client: AsyncClient, account_factory
):
    account = await account_factory(institution_acc_name="GBP General")
    csv_bytes = cases_to_csv(ACCOUNT_CASES, ACCOUNT_HEADER)
    expected = counts(ACCOUNT_CASES)

    response = await auth_client.post(
        f"/uploads?account_id={account['id']}", files=_upload_file(csv_bytes)
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert body["counters"] == {
        "total_rows": len(ACCOUNT_CASES),
        "parsed": expected["parsed"],
        "saved": expected["parsed"],
        "duplicates": 0,
        "skipped": expected["skipped"],
        "failed": expected["failed"],
    }
    assert body["has_internal_errors"] is False
    assert body["issues_truncated"] is False

    # Every issue must point at a locatable row.
    for issue in body["skipped"] + body["failed"]:
        assert issue["row_number"] is not None
        assert issue["line_number"] == issue["row_number"] + 1  # header offset

    # The response id is the same id the logs are tagged with.
    assert response.headers["X-Request-ID"] == body["upload_id"]

    # Re-uploading the same file must import nothing new.
    again = await auth_client.post(
        f"/uploads?account_id={account['id']}", files=_upload_file(csv_bytes)
    )

    assert again.status_code == 200, again.text
    repeat = again.json()["counters"]
    assert repeat["saved"] == 0
    assert repeat["duplicates"] == expected["parsed"]


async def test_identical_rows_are_all_kept_and_stay_idempotent(
    auth_client: AsyncClient, account_factory
):
    """A statement may legitimately repeat the same row. All copies must be
    imported, and re-uploading must still add nothing."""
    account = await account_factory()
    csv_bytes = to_csv_bytes(SAVING_HEADER, REPEATED_SAVING_ROWS)

    first = await auth_client.post(
        f"/uploads?account_id={account['id']}", files=_upload_file(csv_bytes)
    )

    assert first.status_code == 200, first.text
    assert first.json()["counters"]["saved"] == len(REPEATED_SAVING_ROWS)

    second = await auth_client.post(
        f"/uploads?account_id={account['id']}", files=_upload_file(csv_bytes)
    )

    assert second.status_code == 200, second.text
    counters = second.json()["counters"]
    assert counters["saved"] == 0
    assert counters["duplicates"] == len(REPEATED_SAVING_ROWS)


async def test_upload_rejects_unknown_format(
    auth_client: AsyncClient, account_factory
):
    account = await account_factory()
    csv_bytes = to_csv_bytes(UNKNOWN_HEADER, UNKNOWN_ROWS)

    response = await auth_client.post(
        f"/uploads?account_id={account['id']}", files=_upload_file(csv_bytes)
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "csv_format_unknown"
    assert body["request_id"]
    assert body["details"]["headers"] == UNKNOWN_HEADER
    # A clean message, not a stacktrace.
    assert "Traceback" not in body["message"]


async def test_upload_rejects_unknown_account(auth_client: AsyncClient):
    missing = "00000000-0000-0000-0000-000000000000"

    response = await auth_client.post(
        f"/uploads?account_id={missing}",
        files=_upload_file(cases_to_csv(ACCOUNT_CASES, ACCOUNT_HEADER)),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "account_not_found"
