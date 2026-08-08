import hashlib
import io
from csv import DictReader

from fastapi import UploadFile

from app.models import Account, Transaction
from app.services.institution_parser import get_parser


def build_dedup_hash(transaction: Transaction) -> str:
    data = (
        str(transaction.account_id)
        + str(transaction.start_date.isoformat())
        + str(transaction.merchant)
        + str(transaction.amount)
    )
    return hashlib.sha256(data.encode()).hexdigest()


async def parse_csv(file: UploadFile) -> list[dict]:
    contents = await file.read()
    text = contents.decode("utf-8")
    return list(DictReader(io.StringIO(text)))


async def parse_transactions(
    file: UploadFile, current_account: Account, accounts: list[Account]
) -> tuple[list[Transaction], list[dict]]:
    raw_transactions = await parse_csv(file)
    parser = get_parser(current_account.institution, accounts)
    transactions = parser.parse(raw_transactions)
    for tr in transactions:
        tr.account_id = current_account.id
        tr.dedup_hash = build_dedup_hash(transaction=tr)
    return transactions, parser.errors
