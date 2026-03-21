from pydantic_settings import BaseSettings, SettingsConfigDict

from .constants import AppMode


class AppBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DataBaseSettings(AppBaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"

    @property
    def sql_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}/{self.postgres_db}"
        )


class ProjectSettings(AppBaseSettings):
    app_mode: AppMode


class AppSettings:
    data_base: DataBaseSettings
    project: ProjectSettings

    def __init__(self):
        self.data_base = DataBaseSettings()
        self.project = ProjectSettings()


settings = AppSettings()
