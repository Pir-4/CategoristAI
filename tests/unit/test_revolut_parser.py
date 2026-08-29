"""Revolut parser behaviour. No database, no mocks — the parser turns rows
into unsaved model objects, which needs neither."""

import pytest

from app.core.exceptions import UnknownCsvFormatError
from app.services.institution_parser.revolut import RevolutParser
from app.services.institution_parser.rows import CsvRow
from tests.test_data.revolut_cases import (
    ACCOUNT_CASES,
    ACCOUNT_HEADER,
    OWN_ACCOUNT_NAMES,
    SAVING_CASES,
    SAVING_HEADER,
    UNKNOWN_HEADER,
    RevolutCase,
)


class _Account:
    """Only institution_acc_name is read by the parser."""

    def __init__(self, institution_acc_name: str):
        self.institution_acc_name = institution_acc_name


def _parse_one(case: RevolutCase, header: list[str]):
    parser = RevolutParser([_Account(name) for name in OWN_ACCOUNT_NAMES])
    parser.prepare(header)
    return parser.parse([CsvRow(number=1, line=2, data=case.row)])


def _assert_case(case: RevolutCase, header: list[str]) -> None:
    outcome = _parse_one(case, header)

    if case.outcome == "parsed":
        assert not outcome.failed, outcome.failed
        assert not outcome.skipped, outcome.skipped
        assert len(outcome.parsed) == 1
        transaction = outcome.parsed[0].transaction

        if case.transaction_type is not None:
            assert transaction.transaction_type == case.transaction_type
        if case.amount is not None:
            assert transaction.amount == case.amount
        if case.fee is not None:
            assert transaction.fee == case.fee
        if case.merchant is not None:
            assert transaction.merchant == case.merchant
        if case.start_date is not None:
            assert transaction.start_date == case.start_date
        if case.completed_date is not None:
            assert transaction.completed_date == case.completed_date
        # The raw row is always kept for debugging.
        assert transaction.raw_data == case.row

    elif case.outcome == "skipped":
        assert not outcome.failed, outcome.failed
        assert not outcome.parsed
        assert len(outcome.skipped) == 1
        assert outcome.skipped[0].code == case.code

    else:
        assert not outcome.parsed
        assert len(outcome.failed) == 1
        issue = outcome.failed[0]
        assert issue.code == case.code
        # The user must be able to find the row in their file.
        assert issue.row_number == 1
        assert issue.line_number == 2


@pytest.mark.parametrize(
    "case", ACCOUNT_CASES, ids=[case.id for case in ACCOUNT_CASES]
)
def test_account_row(case: RevolutCase):
    _assert_case(case, ACCOUNT_HEADER)


@pytest.mark.parametrize(
    "case", SAVING_CASES, ids=[case.id for case in SAVING_CASES]
)
def test_saving_row(case: RevolutCase):
    _assert_case(case, SAVING_HEADER)


def test_unknown_header_rejects_whole_file():
    """An unrecognised file fails once, not once per row."""
    parser = RevolutParser([])

    with pytest.raises(UnknownCsvFormatError) as excinfo:
        parser.prepare(UNKNOWN_HEADER)

    assert excinfo.value.context["headers"] == UNKNOWN_HEADER


def test_parser_bug_becomes_internal_error_without_aborting():
    """A crash inside the parser must be reported as an internal error for
    that row, keep its traceback, and leave the other rows importable."""

    class BuggyParser(RevolutParser):
        def check_to_skip_tr(self, row):
            return row.data["NoSuchColumn"]  # deliberate KeyError

    parser = BuggyParser([])
    parser.prepare(ACCOUNT_HEADER)
    good_row = ACCOUNT_CASES[0].row

    outcome = parser.parse(
        [
            CsvRow(number=1, line=2, data=good_row),
            CsvRow(number=2, line=3, data=good_row),
        ]
    )

    assert len(outcome.failed) == 2
    assert outcome.has_internal_errors
    # The client gets a generic message; the detail lives in the logs.
    assert "NoSuchColumn" not in outcome.failed[0].message
    assert [issue.row_number for issue in outcome.failed] == [1, 2]
