from .v1 import auth_router, user_router, user_accounts

v1_routers = [user_router, auth_router, user_accounts]

__all__ = ["v1_routers"]
