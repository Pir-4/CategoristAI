from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as user_router

__all__ = [
    "user_router",
    "auth_router",
]
