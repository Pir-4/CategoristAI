from fastapi import FastAPI

from app.api import v1_routers
from app.core import setup_logging

app = FastAPI()
setup_logging()

for router in v1_routers:
    app.include_router(router)
