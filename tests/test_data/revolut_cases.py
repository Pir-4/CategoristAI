"""Revolut CSV cases — the single source of truth for the test suite.

Every case is a real shape observed in a genuine Revolut export, with all
identifying values replaced: no real brand, city, employer, person, amount or
date survives. The *structure* is preserved byte for byte (quoting, the pound
sign, thousands separators, blank fields), because that structure is what the
parser actually has to cope with.

Used twice:
  * unit tests parametrize over these lists;
  * the e2e test writes the same rows to a CSV and uploads it.
"""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.core import ErrorCode, SkipReason, TransactionType

ACCOUNT_HEADER = [
    "Type",
    "Product",
    "Started Date",
    "Completed Date",
    "Description",
    "Amount",
    "Fee",
    "Currency",
    "State",
    "Balance",
]

SAVING_HEADER = ["Date", "Description", "Money out", "Money in", "Balance"]

# Account names the parser is given; a description containing one of these
# makes a Transfer internal rather than external.
OWN_ACCOUNT_NAMES = ["GBP Savings", "GBP General"]

MERCHANT_MAX_LENGTH = 150
_LONG_DESCRIPTION = "Very Long Merchant Name " * 10  # 240 chars


@dataclass(frozen=True)
class RevolutCase:
    """One CSV row plus what the parser must make of it."""

    id: str
    row: dict[str, str]
    outcome: Literal["parsed", "skipped", "failed"]

    transaction_type: TransactionType | None = None
    amount: Decimal | None = None
    fee: Decimal | None = None
    merchant: str | None = None
    start_date: datetime | None = None
    completed_date: datetime | None = None

    code: ErrorCode | SkipReason | None = None


def _account_row(
    type_: str,
    started: str,
    completed: str,
    description: str,
    amount: str,
    state: str = "COMPLETED",
    fee: str = "0.00",
    product: str = "Current",
    balance: str = "100.00",
) -> dict[str, str]:
    return {
        "Type": type_,
        "Product": product,
        "Started Date": started,
        "Completed Date": completed,
        "Description": description,
        "Amount": amount,
        "Fee": fee,
        "Currency": "GBP",
        "State": state,
        "Balance": balance,
    }


def _saving_row(
    date: str, description: str, out: str, in_: str, balance: str
) -> dict[str, str]:
    return {
        "Date": date,
        "Description": description,
        "Money out": out,
        "Money in": in_,
        "Balance": balance,
    }


ACCOUNT_CASES: list[RevolutCase] = [
    RevolutCase(
        id="card_payment_is_expense",
        row=_account_row(
            "Card Payment",
            "2025-03-31 19:50:16",
            "2025-04-01 18:08:55",
            "Coffee Shop",
            "-12.50",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("-12.50"),
        fee=Decimal("0.00"),
        merchant="Coffee Shop",
        completed_date=datetime(2025, 4, 1, 18, 8, 55),
    ),
    RevolutCase(
        # A pending card payment already moves the balance in the Revolut app,
        # so it must be imported, not skipped.
        id="card_payment_pending_is_kept",
        row=_account_row(
            "Card Payment",
            "2026-08-23 04:15:25",
            "",
            "Transit Operator",
            "-1.75",
            state="PENDING",
            balance="",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("-1.75"),
        # Completed Date is blank -> falls back to Started Date.
        completed_date=datetime(2026, 8, 23, 4, 15, 25),
    ),
    RevolutCase(
        # A refund is only real once it completes.
        id="card_refund_pending_is_skipped",
        row=_account_row(
            "Card Refund",
            "2026-08-23 12:14:20",
            "",
            "Pet Store",
            "2.06",
            state="PENDING",
            balance="",
        ),
        outcome="skipped",
        code=SkipReason.PENDING_REFUND,
    ),
    RevolutCase(
        id="reverted_row_falls_back_to_start_date",
        row=_account_row(
            "Card Payment",
            "2025-04-01 10:13:08",
            "",
            "Streaming Service",
            "-1.01",
            state="REVERTED",
            balance="",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        completed_date=datetime(2025, 4, 1, 10, 13, 8),
    ),
    RevolutCase(
        # amount is 0.00 and the real value sits in Fee, so neither sign check
        # fires: the explicit "Charge" branch is what classifies this row.
        id="charge_with_zero_amount_is_expense",
        row=_account_row(
            "Charge",
            "2025-05-28 01:16:12",
            "2025-05-28 01:16:12",
            "Premium plan fee",
            "0.00",
            fee="7.99",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        amount=Decimal("0.00"),
        fee=Decimal("7.99"),
        merchant="Premium plan fee",
    ),
    RevolutCase(
        id="transfer_naming_own_account_is_internal",
        row=_account_row(
            "Transfer",
            "2025-04-12 10:59:09",
            "2025-04-12 10:59:09",
            "To pocket GBP Savings from GBP",
            "500.00",
            product="Savings",
        ),
        outcome="parsed",
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        merchant="pocket GBP Savings from GBP",
    ),
    RevolutCase(
        id="transfer_to_person_is_external",
        row=_account_row(
            "Transfer",
            "2025-05-01 17:15:57",
            "2025-05-01 17:15:58",
            "Transfer to Alice Example",
            "-150.00",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXTERNAL_TRANSFER,
        merchant="Alice Example",
    ),
    RevolutCase(
        id="topup_strips_payment_from_prefix",
        row=_account_row(
            "Topup",
            "2025-04-11 13:34:56",
            "2025-04-11 13:34:57",
            "Payment from ACME PAYROLL LTD",
            "2500.00",
        ),
        outcome="parsed",
        transaction_type=TransactionType.INCOME,
        merchant="ACME PAYROLL LTD",
    ),
    RevolutCase(
        id="positive_exchange_is_income",
        row=_account_row(
            "Exchange",
            "2025-04-28 15:30:45",
            "2025-04-28 15:30:45",
            "Exchanged to GBP",
            "1200.00",
        ),
        outcome="parsed",
        transaction_type=TransactionType.INCOME,
        merchant="Exchanged to GBP",
    ),
    RevolutCase(
        id="completed_card_refund_is_income",
        row=_account_row(
            "Card Refund",
            "2025-10-16 11:53:46",
            "2025-10-17 10:44:51",
            "Rail Operator",
            "420.00",
        ),
        outcome="parsed",
        transaction_type=TransactionType.INCOME,
        merchant="Rail Operator",
    ),
    RevolutCase(
        id="negative_uncommon_type_is_expense",
        row=_account_row(
            "Chargeback Reversal",
            "2026-03-10 10:25:30",
            "2026-03-10 10:25:30",
            "Reverted refund for Flower Shop claim",
            "-68.89",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        merchant="Reverted refund for Flower Shop claim",
    ),
    RevolutCase(
        id="transfer_without_prefix_keeps_description",
        row=_account_row(
            "Transfer",
            "2025-03-31 20:31:38",
            "2025-03-31 20:31:38",
            "Pocket Withdrawal",
            "-328.00",
            product="Savings",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXTERNAL_TRANSFER,
        merchant="Pocket Withdrawal",
    ),
    RevolutCase(
        # Revolut sometimes drops the leading zero on the hour.
        id="single_digit_hour_is_padded",
        row=_account_row(
            "Card Payment",
            "2026-04-28 7:48:25",
            "2026-04-28 7:48:25",
            "Online Service*Metro",
            "-20.00",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        start_date=datetime(2026, 4, 28, 7, 48, 25),
    ),
    RevolutCase(
        # Regression: get_transaction_type once used `in "Charge"`, a substring
        # test, so any single character matched and was silently called an
        # expense. With amount 0.00 no sign check can rescue it either.
        id="single_char_type_is_not_a_charge",
        row=_account_row(
            "C",
            "2025-06-01 10:00:00",
            "2025-06-01 10:00:00",
            "Substring Regression",
            "0.00",
        ),
        outcome="failed",
        code=ErrorCode.ROW_UNKNOWN_TRANSACTION_TYPE,
    ),
    RevolutCase(
        id="unknown_state_is_reported",
        row=_account_row(
            "Card Payment",
            "2025-06-02 10:00:00",
            "",
            "Mystery State",
            "-5.00",
            state="SCHEDULED",
            balance="",
        ),
        outcome="failed",
        code=ErrorCode.ROW_UNKNOWN_STATE,
    ),
    RevolutCase(
        id="unparsable_date_is_reported",
        row=_account_row(
            "Card Payment",
            "not-a-date",
            "",
            "Broken Date",
            "-5.00",
        ),
        outcome="failed",
        code=ErrorCode.ROW_VALIDATION_FAILED,
    ),
    RevolutCase(
        # merchant is String(150) in the database.
        id="long_description_is_truncated",
        row=_account_row(
            "Card Payment",
            "2025-06-03 10:00:00",
            "2025-06-03 10:00:00",
            _LONG_DESCRIPTION,
            "-9.99",
        ),
        outcome="parsed",
        transaction_type=TransactionType.EXPENSE,
        merchant=_LONG_DESCRIPTION[:MERCHANT_MAX_LENGTH],
    ),
]


SAVING_CASES: list[RevolutCase] = [
    RevolutCase(
        id="deposit_is_internal_transfer",
        row=_saving_row("13 Jul 2025", "Deposit", "", "£2,100.00", "£2,100.00"),
        outcome="parsed",
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("2100.00"),
        # Set explicitly by the parser: the column default only applies at
        # INSERT, and None would end up as the string "None" in the hash.
        fee=Decimal("0"),
        merchant="Deposit",
    ),
    RevolutCase(
        id="withdrawal_is_negative_internal_transfer",
        row=_saving_row(
            "15 Jul 2025", "Withdrawal", "£100.00", "", "£2,000.42"
        ),
        outcome="parsed",
        transaction_type=TransactionType.INTERNAL_TRANSFER,
        amount=Decimal("-100.00"),
        merchant="Withdrawal",
    ),
    RevolutCase(
        id="gross_interest_is_interest",
        row=_saving_row(
            "14 Jul 2025", "Gross Interest", "", "£0.21", "£2,100.21"
        ),
        outcome="parsed",
        transaction_type=TransactionType.INTEREST,
        amount=Decimal("0.21"),
        merchant="Gross Interest",
    ),
    RevolutCase(
        # Revolut writes a four-letter "Sept", which %b does not accept.
        id="four_letter_sept_is_parsed",
        row=_saving_row(
            "1 Sept 2025", "Gross Interest", "", "£0.01", "£106.29"
        ),
        outcome="parsed",
        transaction_type=TransactionType.INTEREST,
        amount=Decimal("0.01"),
        start_date=datetime(2025, 9, 1),
    ),
    RevolutCase(
        id="unknown_saving_operation_is_reported",
        row=_saving_row("1 Aug 2025", "Bonus", "", "£5.00", "£10.00"),
        outcome="failed",
        code=ErrorCode.ROW_UNKNOWN_SAVING_OPERATION,
    ),
    RevolutCase(
        # Would otherwise reach the database as amount=None and kill the whole
        # batch with a NOT NULL violation, with no row to blame.
        id="deposit_without_amount_is_reported",
        row=_saving_row("2 Aug 2025", "Deposit", "", "", "£10.00"),
        outcome="failed",
        code=ErrorCode.ROW_SAVING_AMOUNT_MISSING,
    ),
]


def to_csv_bytes(header: list[str], rows: list[dict[str, str]]) -> bytes:
    """Render rows as a CSV file body, the way the bank would."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=header)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def cases_to_csv(cases: list[RevolutCase], header: list[str]) -> bytes:
    return to_csv_bytes(header, [case.row for case in cases])


def counts(cases: list[RevolutCase]) -> dict[str, int]:
    """Expected parsed/skipped/failed totals for a list of cases."""
    result = {"parsed": 0, "skipped": 0, "failed": 0}
    for case in cases:
        result[case.outcome] += 1
    return result


UNKNOWN_HEADER = ["Foo", "Bar"]
UNKNOWN_ROWS: list[dict[str, str]] = [
    {"Foo": "1", "Bar": "2"},
    {"Foo": "3", "Bar": "4"},
]
