import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import settings
from .constants import AppMode

FORMAT = " [%(asctime)s] %(levelname)s %(name)s: %(message)s"


def setup_logging():
    formatter = logging.Formatter(FORMAT)
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    logger.setLevel(logging.DEBUG)
    if settings.project.app_mode == AppMode.PROD:
        Path(settings.project.log_file).parent.mkdir(
            parents=True, exist_ok=True
        )
        handler = RotatingFileHandler(
            filename=settings.project.log_file,
            maxBytes=settings.project.log_max_bytes,
            backupCount=settings.project.log_backup_count,
        )
        logger.setLevel(logging.INFO)

    handler.setFormatter(formatter)
    logger.addHandler(handler)
