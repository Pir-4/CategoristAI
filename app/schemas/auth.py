from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=30, title="User login")
    password: str = Field(min_length=5, title="User password")


class TokenResponse(BaseModel):
    token_type: str = "bearer"
    access_token: str
    refresh_token: str
