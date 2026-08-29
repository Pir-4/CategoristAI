import logging

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import AppMode, LogFormat


class AppBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DataBaseSettings(AppBaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_test_db: str
    postgres_host: str = "localhost"

    @property
    def sql_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}/{self.postgres_db}"
        )

    @property
    def test_sql_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}/{self.postgres_test_db}"
        )


class ProjectSettings(AppBaseSettings):
    app_mode: AppMode


class LoggingSettings(AppBaseSettings):
    """Everything here is optional: None means "derive from app_mode"."""

    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="log_"
    )

    level: str | None = None
    format: LogFormat | None = None
    file: str | None = None
    max_bytes: int = 10_000_000
    backup_count: int = 2

    @field_validator("level")
    @classmethod
    def normalize_level(cls, value: str | None) -> str | None:
        if value is None:
            return None
        upper = value.upper()
        if upper not in logging.getLevelNamesMapping():
            raise ValueError(f"Unknown log level: {value}")
        return upper

    def resolve(self, app_mode: AppMode) -> tuple[int, LogFormat]:
        is_prod = app_mode is AppMode.PROD
        level_name = self.level or ("INFO" if is_prod else "DEBUG")
        log_format = self.format or (
            LogFormat.JSON if is_prod else LogFormat.CONSOLE
        )
        return logging.getLevelNamesMapping()[level_name], log_format


class UploadSettings(AppBaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_prefix="upload_"
    )

    max_bytes: int = 20_000_000
    max_issues_in_response: int = 200
    max_logged_failures: int = 100


class SecuritySettings(AppBaseSettings):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 2


class AppSettings:
    data_base: DataBaseSettings
    project: ProjectSettings
    security: SecuritySettings
    logging: LoggingSettings
    upload: UploadSettings

    def __init__(self):
        self.data_base = DataBaseSettings()
        self.project = ProjectSettings()
        self.security = SecuritySettings()
        self.logging = LoggingSettings()
        self.upload = UploadSettings()


settings = AppSettings()
