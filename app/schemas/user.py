from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    login: str = Field(min_length=1, max_length=30, title="User login")
    password: str = Field(min_length=5, title="User password")


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., title="User ID", description="UUID v4")
    login: str = Field(min_length=1, max_length=30, title="User login")
    created_at: datetime = Field(...)


class UserUpdate(BaseModel):
    login: str | None = Field(
        min_length=1, max_length=30, title="User login", default=None
    )
    password: str | None = Field(
        min_length=5, title="User password", default=None
    )
