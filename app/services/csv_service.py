import hashlib
import io
from csv import DictReader

from fastapi import UploadFile

from app.models import Account, Transaction
from app.services.bank_parser import BankParser, Banks


def build_dedup_hash(date: str, merchant: str | None, amount: str) -> str:
    data = date + str(merchant) + amount
    return hashlib.sha256(data.encode()).hexdigest()


async def parse_csv(file: UploadFile) -> list[dict]:
    contents = await file.read()
    text = contents.decode("utf-8")
    return list(DictReader(io.StringIO(text)))


async def parse_transactions(
    file: UploadFile, bank: Banks, accounts: list[Account]
) -> list[Transaction]:
    raw_transactions = await parse_csv(file)
    transactions = BankParser.get_parser(bank).parse(raw_transactions, accounts)
    for transaction in transactions:
        transaction.dedup_hash = build_dedup_hash(
            date=str(transaction.date),
            merchant=transaction.merchant,
            amount=str(transaction.amount),
        )
    return transactions
