from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core import AccountType


class AccountCreate(BaseModel):
    name: str = Field(min_length=5, max_length=30, title="Account name")
    account_type: AccountType
    initial_balance: Decimal
    is_categorizable: bool = Field(default=True)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    account_type: AccountType
    keywords: list[str]
    initial_balance: Decimal
    current_balance: Decimal
    is_categorizable: bool
    is_active: bool

    @field_validator("keywords", mode="before")
    @classmethod
    def extract_keywords(cls, v):
        return [kw.keyword for kw in v]


class KeywordCreate(BaseModel):
    keyword: str = Field(min_length=5, max_length=100)
