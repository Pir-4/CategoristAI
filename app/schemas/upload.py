from pydantic import BaseModel
from .transactions import TransactionResponse


class UploadResult(BaseModel):
    transactions: list[TransactionResponse]
    errors: list[dict]
