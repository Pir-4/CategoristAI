from .v1 import auth_router, user_router, user_accounts, upload_files

v1_routers = [user_router, auth_router, user_accounts, upload_files]

__all__ = ["v1_routers"]
