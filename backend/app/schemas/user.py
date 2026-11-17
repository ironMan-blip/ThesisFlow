from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, ValidationInfo, computed_field, field_validator

from app.config import settings
from app.models.milestone import Phase
from app.models.user import DELETION_DAYS, REVIEW_HOURS, Role
from app.passwords import MAX_PASSWORD, MIN_PASSWORD, PASSWORD_HINT, check_strength


# A reason in a sentence or more, never a single word: every delete is explained, by whoever asks for it.
MIN_REASON_CHARS, MAX_REASON_CHARS = 20, 2000

# Sign-up is BRAC University only: students use the student domain, faculty the staff one.
EMAIL_DOMAINS = {Role.student: "g.bracu.ac.bd", Role.faculty: "bracu.ac.bd"}
MAX_INITIALS = 10  # faculty only


class SignupRoleOut(BaseModel):
    role: Role
    email_domain: str
    needs_initials: bool


class SignupOptionsOut(BaseModel):
    """What the sign-up form shows, from the same rules UserCreate enforces."""

    roles: list[SignupRoleOut] = [
        SignupRoleOut(role=r, email_domain=d, needs_initials=r == Role.faculty) for r, d in EMAIL_DOMAINS.items()
    ]
    min_password: int = MIN_PASSWORD
    max_password: int = MAX_PASSWORD
    password_hint: str = PASSWORD_HINT
    max_initials: int = MAX_INITIALS
    review_hours: int = REVIEW_HOURS


class DeletionReasonIn(BaseModel):
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=MIN_REASON_CHARS, max_length=MAX_REASON_CHARS)]


class UserCreate(BaseModel):
    # Run validators on defaults too, so faculty cannot skip initials by leaving them out.
    model_config = ConfigDict(validate_default=True)

    # Coordinator is the single admin account from settings; nobody can sign up as one.
    # Declared before email so the email check can read it.
    role: Literal[Role.student, Role.faculty] = Role.student
    email: EmailStr
    id_number: str
    # Stripped, so a name of only spaces (empty first name and avatar) is refused.
    full_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    password: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)
    initials: str | None = None  # faculty only

    @field_validator("email")
    @classmethod
    def university_email(cls, v: str, info: ValidationInfo) -> str:
        domain = EMAIL_DOMAINS.get(info.data.get("role"))
        if domain is None:
            return v  # role itself failed validation and is reported on its own
        if not v.lower().endswith("@" + domain):
            raise ValueError(f"{info.data['role'].value.capitalize()} email must end with @{domain}")
        return v

    @field_validator("id_number")
    @classmethod
    def eight_digits(cls, v: str) -> str:
        if not (len(v) == 8 and v.isascii() and v.isdigit()):
            raise ValueError("ID number must be exactly 8 digits")
        return v

    @field_validator("password")
    @classmethod
    def strong_password(cls, v: str) -> str:
        return check_strength(v)

    @field_validator("initials")
    @classmethod
    def faculty_initials(cls, v: str | None, info: ValidationInfo) -> str | None:
        if info.data.get("role") != Role.faculty:
            return None
        v = (v or "").strip().upper()  # "mmr" and "MMR" are the same initials
        if not v:
            raise ValueError("Faculty must give their initials")
        if not (len(v) <= MAX_INITIALS and v.isascii() and v.isalpha()):
            raise ValueError(f"Initials must be 1 to {MAX_INITIALS} letters")
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
    phase: Phase | None  # students only
    restart_pending: bool
    review_hours: int = REVIEW_HOURS  # coordinator's decision window, for page text
    # The account's own scheduled deletion, if any, and the limits every delete form uses.
    deletion_executes_at: datetime | None  # None until the coordinator approves
    deletion_reason: str | None
    deletion_by_coordinator: bool
    deletion_days: int = DELETION_DAYS
    min_reason_chars: int = MIN_REASON_CHARS
    max_reason_chars: int = MAX_REASON_CHARS

    @computed_field
    @property
    def coordinator_contact(self) -> str | None:
        # Only with a deletion the coordinator scheduled: the owner is told to contact them before it runs.
        return settings.admin_email if self.deletion_by_coordinator else None


class RegistrationRequestOut(UserOut):
    created_at: datetime


class DeletionRequestOut(UserOut):
    deletion_requested_at: datetime


class RestartRequestOut(UserOut):
    restart_requested_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
