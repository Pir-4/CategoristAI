from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DataBaseSettings(AppBaseSettings):
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "localhost"
    vector_url: AnyUrl = Field(validation_alias="VECTOR_DB_URL")

    @property
    def sql_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}/{self.postgres_db}"
        )


class AppSettings:
    data_base: DataBaseSettings

    def __init__(self):
        self.data_base = DataBaseSettings()


settings = AppSettings()
