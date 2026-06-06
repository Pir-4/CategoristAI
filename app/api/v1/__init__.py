from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as user_router
from app.api.v1.accounts import router as user_accounts

__all__ = [
    "user_router",
    "auth_router",
    "user_accounts",
]
