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
    institution_acc_name: str
    is_active: bool


class AccountUpdate(BaseModel):
    name: str | None = None
    institution: Institution | None = None
    institution_acc_name: str | None = None
    is_active: bool | None = None
