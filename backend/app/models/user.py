import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(str, enum.Enum):
    student = "student"
    # A faculty member can be a supervisor and a panel member; that is decided
    # per group / per defense, not by the account role.
    faculty = "faculty"
    coordinator = "coordinator"


# Pages each role can open; the frontend shows exactly these in nav and dashboard.
# The coordinator has no "account" tool: that account can never be deleted.
ROLE_TOOLS = {
    Role.student: ["proposal", "deadlines", "account"],
    Role.faculty: ["deadlines", "account"],
    Role.coordinator: ["deadlines", "accounts", "registration_requests", "deletion_requests"],
}

# The coordinator has this long to decide a sign-up or an account deletion request.
REVIEW_WINDOW = timedelta(hours=48)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    # 8-digit university ID; this is what users log in with.
    id_number: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    # Faculty only, e.g. "MMR"; uppercase letters, unique among faculty.
    initials: Mapped[str | None] = mapped_column(String(10), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"))
    # Sign-ups start unapproved and cannot log in until the coordinator approves them.
    approved: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when the user asks to delete their account; the request lapses after REVIEW_WINDOW.
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def tools(self) -> list[str]:
        return ROLE_TOOLS[self.role]

    @property
    def deletion_pending(self) -> bool:
        at = self.deletion_requested_at
        return at is not None and datetime.now(timezone.utc) < at + REVIEW_WINDOW
