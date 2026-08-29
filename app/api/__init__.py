from .v1 import (
    auth_router,
    user_router,
    user_accounts,
    upload_files_router,
    transactions_router,
)

v1_routers = [
    user_router,
    auth_router,
    user_accounts,
    upload_files_router,
    transactions_router,
]

__all__ = ["v1_routers"]
