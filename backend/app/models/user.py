import enum
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.milestone import Phase


class Role(str, enum.Enum):
    student = "student"
    # A faculty member can be a supervisor and a panel member; that is decided
    # per group / per defense, not by the account role.
    faculty = "faculty"
    coordinator = "coordinator"


# Pages each role can open; the frontend shows exactly these in nav and dashboard.
# The coordinator has no "account" tool: that account can never be deleted.
ROLE_TOOLS = {
    Role.student: ["thesis", "proposal", "deadlines", "account"],
    Role.faculty: ["theses", "deadlines", "account"],
    Role.coordinator: ["theses", "deadlines", "accounts", "registration_requests", "deletion_requests", "restart_requests"],
}

# The coordinator has this long to decide a sign-up or an account deletion request.
REVIEW_WINDOW = timedelta(hours=48)
REVIEW_HOURS = REVIEW_WINDOW // timedelta(hours=1)


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

    # Students only. The current thesis group (pending or active); faculty are linked from the thesis row instead.
    thesis_id: Mapped[int | None] = mapped_column(ForeignKey("theses.id", ondelete="SET NULL", use_alter=True, name="users_thesis_id_fkey"))
    # Students only: the phase they are in this semester. Null once the thesis is completed.
    phase: Mapped[Phase | None] = mapped_column(Enum(Phase, name="phase"))
    # When the current phase started (sign-up, rollover or restart); only uploads after it count.
    phase_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    # Set at the semester rollover for a missed deadline or a second P3 deferral.
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # A frozen student asked the coordinator to restart at P1.
    restart_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # post_update: users and theses point at each other, so this link is written in a second UPDATE.
    thesis = relationship("Thesis", foreign_keys=[thesis_id], post_update=True)

    @property
    def tools(self) -> list[str]:
        return ROLE_TOOLS[self.role]

    @property
    def first_name(self) -> str:
        return (self.full_name.split() or [""])[0]

    @property
    def monogram(self) -> str:
        # Avatar letters, e.g. "Ada Byron King" -> "AB".
        return "".join(p[0] for p in self.full_name.split()[:2]).upper()

    @property
    def restart_pending(self) -> bool:
        return self.restart_requested_at is not None

    @property
    def deletion_pending(self) -> bool:
        at = self.deletion_requested_at
        return at is not None and datetime.now(timezone.utc) < at + REVIEW_WINDOW
