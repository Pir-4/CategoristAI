import structlog
from fastapi import FastAPI

from app.api import v1_routers
from app.core import setup_logging

app = FastAPI()
setup_logging()

logger = structlog.get_logger(__name__)

logger.info("Starting CategoristAI...")
for router in v1_routers:
    app.include_router(router)
logger.info("Routers connected.")
