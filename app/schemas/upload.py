from pydantic import BaseModel
from app.schemas import TransactionResponse


class UploadResult(BaseModel):
    transactions: list[TransactionResponse]
    errors: list[dict]
