"""Shapes for the accounts, categories and transactions the suite seeds.

Derived from what actually exists rather than invented:

* both accounts in the database are ``revolut`` / "GBP General", and one of
  the two is deactivated - so ``is_active`` really does get toggled;
* the real exports carry no fee on 2696 of 2710 account rows, so zero is the
  representative fee;
* the savings exports contain 52 groups of rows identical in date,
  description and amount (up to three copies of one), which is precisely the
  collision the identity constraint and the ``occurrence`` counter exist for -
  and what a merchant edit can walk into.

Values are anonymised: the institution and the institution account name are
product labels Revolut gives every customer, everything else is invented.
"""

from datetime import datetime
from decimal import Decimal

from app.core import Institution, TransactionType

SEED_INSTITUTION = Institution.REVOLUT
SEED_INSTITUTION_ACC_NAME = "GBP General"

SEED_START_DATE = datetime(2026, 3, 4, 9, 15)
SEED_AMOUNT = Decimal("12.34")
SEED_FEE = Decimal("0.00")
SEED_TRANSACTION_TYPE = TransactionType.EXPENSE
