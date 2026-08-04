from enum import Enum, StrEnum, auto

from .base import BankParserBase
from .revolut import RevolutParser


class Banks(StrEnum):
    REVOLUT = auto()


class BankParser(Enum):
    def __init__(self, bank_name: Banks, parser: BankParserBase):
        self.bank_name = bank_name
        self.parser = parser

    Revolut = (Banks.REVOLUT, RevolutParser())

    @classmethod
    def get_parser(cls, bank_name: Banks = Banks.REVOLUT) -> BankParserBase:
        try:
            return next(
                bank_parser.parser
                for bank_parser in cls
                if bank_parser.bank_name == bank_name
            )
        except StopIteration as ex:
            raise ValueError(f"Bank with name {bank_name} is not found") from ex
