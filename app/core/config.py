from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import AppMode


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
    log_file: str = "logs/app.log"
    log_max_bytes: int = 10_000_000
    log_backup_count: int = 2


class SecuritySettings(AppBaseSettings):
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 2


class AppSettings:
    data_base: DataBaseSettings
    project: ProjectSettings
    security: SecuritySettings

    def __init__(self):
        self.data_base = DataBaseSettings()
        self.project = ProjectSettings()
        self.security = SecuritySettings()


settings = AppSettings()
