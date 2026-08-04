from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    total_count: int
    upload_at: datetime
    status: str
