from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # Coordinator is the single admin account from settings; nobody can sign up as one.
    role: Literal[Role.student, Role.faculty] = Role.student


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # plain str: stored emails were validated on input; re-validating rejects seeded .test domains
    email: str
    full_name: str
    role: Role
    approved: bool


class FacultyRequestOut(UserOut):
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
