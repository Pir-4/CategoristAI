from .v1 import auth_router, user_router

v1_routers = [user_router, auth_router]

__all__ = ["v1_routers"]
