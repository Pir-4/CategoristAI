from enum import StrEnum, auto

from .revolut import RevolutParser


class Banks(StrEnum):
    REVOLUT = auto()


class BankParser:
    Revolut = RevolutParser()

    @staticmethod
    def get_parser(bank_name: Banks = Banks.REVOLUT):
        if bank_name == Banks.REVOLUT:
            return RevolutParser()
        raise ValueError(f"Bank with names {bank_name} is not found")
