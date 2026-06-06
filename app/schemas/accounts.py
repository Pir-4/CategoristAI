from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core import AccountType


class KeywordCreate(BaseModel):
    keyword: str = Field(min_length=5, max_length=100)


class KeywordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword: str


class AccountCreate(BaseModel):
    name: str = Field(min_length=5, max_length=30, title="Account name")
    account_type: AccountType
    initial_balance: Decimal
    is_categorizable: bool = Field(default=True)
    keywords: list[KeywordCreate] = Field(default_factory=list)


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    account_type: AccountType
    keywords: list[KeywordResponse]
    initial_balance: Decimal
    current_balance: Decimal
    is_categorizable: bool
    is_active: bool
