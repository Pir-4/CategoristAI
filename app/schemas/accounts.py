from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.core import Institution


class KeywordCreate(BaseModel):
    keyword: str = Field(min_length=5, max_length=100)


class KeywordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword: str


class AccountCreate(BaseModel):
    name: str = Field(min_length=5, max_length=30, title="Account name")
    institution: Institution
    initial_balance: Decimal
    keywords: list[KeywordCreate] = Field(default_factory=list)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    institution: Institution
    keywords: list[KeywordResponse]
    initial_balance: Decimal
    current_balance: Decimal
    is_active: bool
