from enum import StrEnum


class AppMode(StrEnum):
    DEV = "development"
    PROD = "production"


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"
