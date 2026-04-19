import hashlib
import io
from csv import DictReader

from fastapi import UploadFile

from app.models import Expense
from app.services.bank_parser import BankParser, Banks


def build_dedup_hash(date: str, merchant: str, amount: str) -> str:
    data = date + merchant + amount
    return hashlib.sha256(data.encode()).hexdigest()


async def parse_csv(file: UploadFile) -> list[dict]:
    contents = await file.read()
    text = contents.decode("utf-8")
    return list(DictReader(io.StringIO(text)))


async def parse_expenses(file: UploadFile, bank: Banks) -> list[Expense]:
    raw_transactions = await parse_csv(file)
    expenses = BankParser.get_parser(bank).parse(raw_transactions)
    for expense in expenses:
        expense.dedup_hash = build_dedup_hash(
            date=str(expense.date),
            merchant=expense.merchant,
            amount=str(expense.amount),
        )
    return expenses
