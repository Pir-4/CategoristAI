from pydantic import AnyUrl, Field, PostgresDsn
from pydantic_settings import BaseSettings


class DataBaseSettings(BaseSettings):
    sql_url: PostgresDsn = Field(validation_alias="DATABASE_URL")
    vector_url: AnyUrl = Field(validation_alias="VECTOR_DB_URL")
