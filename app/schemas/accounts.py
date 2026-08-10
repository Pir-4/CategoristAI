from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.core import Institution


class AccountCreate(BaseModel):
    name: str = Field(min_length=5, max_length=30, title="Account name")
    institution: Institution
    institution_acc_name: str = Field(
        max_length=100,
        title="Institution account name",
        description=(
            "Name used by the institution in transaction descriptions "
            "to identify this account (e.g. 'GBP Savings')"
        ),
    )


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    institution: Institution
    initial_balance: Decimal
    current_balance: Decimal
    is_active: bool
