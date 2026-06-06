import logging
import sys

import structlog

from .config import settings
from .constants import AppMode


def setup_logging() -> None:
    is_prod = settings.project.app_mode == AppMode.PROD
    log_level = logging.INFO if is_prod else logging.DEBUG

    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if is_prod
        else structlog.dev.ConsoleRenderer()
    )

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )

    # stdlib logging для FastAPI, SQLAlchemy etc
    logging.basicConfig(
        level=log_level,
        stream=sys.stdout,
        format="%(levelname)s %(name)s: %(message)s",
    )
