"""Logging setup.

structlog and stdlib ``logging`` are two independent pipelines: our code calls
structlog, while uvicorn / SQLAlchemy / Alembic call stdlib. The previous setup
used ``PrintLoggerFactory``, which printed straight to stdout and bypassed
stdlib entirely - so third-party logs could never share our format.

Here everything converges on a single handler through
``structlog.stdlib.ProcessorFormatter``:

    our code   -> structlog processors -> wrap_for_formatter --.
                                                               |-> Handler
    uvicorn/SA -> stdlib LogRecord -------------------------- -'
                                                               |
                          ProcessorFormatter (foreign_pre_chain for stdlib)
                                        -> one renderer
"""

import hashlib
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.tracebacks import ExceptionDictTransformer

from .config import settings
from .constants import LogFormat

_configured = False

# Number of hex chars kept from the digest: enough to join lines within one
# incident, useless as attack surface.
_FINGERPRINT_CHARS = 12


def fingerprint(value: str) -> str:
    """Stable, non-reversible handle for correlating a secret across lines.

    A secret is never logged, not even truncated (see the standard: JWT
    prefixes are identical per issuer, and password ends are a hint). Log
    this instead, in a field suffixed `_fp` so it cannot be mistaken for the
    value itself.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[
        :_FINGERPRINT_CHARS
    ]


# Third-party loggers we do not want at DEBUG even when we are.
THIRD_PARTY_LEVELS = {
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "asyncio": logging.WARNING,
    "alembic": logging.INFO,
    "uvicorn.access": logging.INFO,
    "python_multipart": logging.WARNING,
}


def _shared_processors(log_format: LogFormat) -> list[Any]:
    """Processors applied to both structlog and stdlib records."""
    processors: list[Any] = [
        # Must be first: copies request_id & friends bound via
        # bind_contextvars() into every event dict.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # Keeps legacy logger.info("text %s", value) calls rendering.
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    if log_format is LogFormat.CONSOLE:
        # Walks the stack on every record - dev only.
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {
                    structlog.processors.CallsiteParameter.MODULE,
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                }
            )
        )
    return processors


def configure_third_party_loggers() -> None:
    """Idempotent. Re-run after uvicorn installs its own log config."""
    for name, level in THIRD_PARTY_LEVELS.items():
        logging.getLogger(name).setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        third_party = logging.getLogger(name)
        third_party.handlers.clear()
        third_party.propagate = True


def setup_logging() -> None:
    """Configure structlog + stdlib once. Safe to call again."""
    global _configured
    if _configured:
        configure_third_party_loggers()
        return

    cfg = settings.logging
    log_level, log_format = cfg.resolve(settings.project.app_mode)
    shared = _shared_processors(log_format)

    structlog.configure(
        processors=[
            # Honours per-logger stdlib levels (THIRD_PARTY_LEVELS).
            structlog.stdlib.filter_by_level,
            *shared,
            # Last: hand the event dict to stdlib instead of rendering.
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    if log_format is LogFormat.JSON:
        renderers: list[Any] = [
            # Structured frames instead of one mangled string.
            # show_locals=False: otherwise every frame dumps every variable.
            structlog.processors.ExceptionRenderer(
                ExceptionDictTransformer(show_locals=False)
            ),
            structlog.processors.JSONRenderer(),
        ]
    else:
        # ConsoleRenderer formats exceptions itself - no dict_tracebacks here.
        renderers = [structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())]

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[structlog.stdlib.ExtraAdder(), *shared],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *renderers,
        ],
    )

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if cfg.file:
        Path(cfg.file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                cfg.file,
                maxBytes=cfg.max_bytes,
                backupCount=cfg.backup_count,
                encoding="utf-8",
            )
        )

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.setLevel(log_level)

    configure_third_party_loggers()
    _configured = True
