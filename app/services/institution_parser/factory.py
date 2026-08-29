import structlog

from app.core.constants import Institution
from app.core.exceptions import UnsupportedInstitutionError
from app.models import Account

from .base import InstitutionParserBase
from .revolut import RevolutParser

logger = structlog.get_logger(__name__)

PARSER_MAP = {
    Institution.REVOLUT: RevolutParser,
}


def get_parser(
    institution: Institution, accounts: list[Account]
) -> InstitutionParserBase:
    parser_class = PARSER_MAP.get(institution)
    if parser_class is None:
        raise UnsupportedInstitutionError(
            institution=str(institution),
            supported=[str(name) for name in PARSER_MAP],
        )
    logger.debug(
        "parser.selected",
        institution=str(institution),
        parser=parser_class.__name__,
    )
    return parser_class(accounts)
