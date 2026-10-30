from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator

from app.models.user import Role


class UserCreate(BaseModel):
    # Run validators on defaults too, so faculty cannot skip initials by leaving them out.
    model_config = ConfigDict(validate_default=True)

    email: EmailStr
    id_number: str
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    # Coordinator is the single admin account from settings; nobody can sign up as one.
    role: Literal[Role.student, Role.faculty] = Role.student
    initials: str | None = None  # faculty only

    @field_validator("id_number")
    @classmethod
    def eight_digits(cls, v: str) -> str:
        if not (len(v) == 8 and v.isascii() and v.isdigit()):
            raise ValueError("ID number must be exactly 8 digits")
        return v

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        if not (any(c.isupper() for c in v) and any(c.islower() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("Password must contain an uppercase letter, a lowercase letter and a number")
        if any(c.isspace() for c in v):
            raise ValueError("Password must not contain spaces")
        return v

    @field_validator("initials")
    @classmethod
    def faculty_initials(cls, v: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("role") != Role.faculty:
            return None
        if not v:
            raise ValueError("Faculty must give their initials")
        if not (len(v) <= 10 and v.isascii() and v.isalpha() and v.isupper()):
            raise ValueError("Initials must be 1 to 10 capital letters")
        return v


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    # plain str: stored emails were validated on input; re-validating rejects seeded .test domains
    email: str
    id_number: str
    full_name: str
    first_name: str
    monogram: str
    initials: str | None
    role: Role
    approved: bool
    tools: list[str]
    deletion_pending: bool


class RegistrationRequestOut(UserOut):
    created_at: datetime


class DeletionRequestOut(UserOut):
    deletion_requested_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
