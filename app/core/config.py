from pydantic import AnyUrl, Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


class DataBaseSettings(AppBaseSettings):
    sql_url: PostgresDsn = Field(validation_alias="DATABASE_URL")
    vector_url: AnyUrl = Field(validation_alias="VECTOR_DB_URL")


class AppSettings:
    data_base: DataBaseSettings

    def __init__(self):
        self.data_base = DataBaseSettings()


settings = AppSettings()
