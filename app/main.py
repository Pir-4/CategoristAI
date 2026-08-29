from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api import v1_routers
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.core import configure_third_party_loggers, settings, setup_logging

setup_logging()

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # uvicorn installs its own logging config after importing this module,
    # so re-tame third-party loggers once the server is actually up.
    configure_third_party_loggers()
    logger.info("app.startup", mode=str(settings.project.app_mode))
    yield
    logger.info("app.shutdown")


app = FastAPI(title="CategoristAI", lifespan=lifespan)

register_exception_handlers(app)
for router in v1_routers:
    app.include_router(router)

# Added last so it wraps everything, including the exception handlers.
app.add_middleware(RequestContextMiddleware)
