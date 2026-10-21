from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: Role


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
