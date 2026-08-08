from app.core.constants import Institution
from app.models import Account
from .base import InstitutionParserBase
from .revolut import RevolutParser

PARSER_MAP = {
    Institution.REVOLUT: RevolutParser,
}


def get_parser(
    institution: Institution, accounts: list[Account]
) -> InstitutionParserBase:
    if institution not in PARSER_MAP:
        raise ValueError(f"No parser for institution: {institution}")
    return PARSER_MAP[institution](accounts)
