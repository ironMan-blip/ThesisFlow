import enum
from datetime import datetime, timedelta

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, false, func, true
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
    Role.student: ["thesis", "teammates", "proposal", "deadlines", "meetings", "account"],
    Role.faculty: ["theses", "deadlines", "meetings", "account"],
    # Semesters (deadlines and the rollover) and accounts only: the coordinator never sees individual theses.
    Role.coordinator: ["deadlines", "accounts", "registration_requests", "deletion_requests", "restart_requests"],
}

# The coordinator has this long to decide a sign-up or an account deletion request.
REVIEW_WINDOW = timedelta(hours=48)
REVIEW_HOURS = REVIEW_WINDOW // timedelta(hours=1)
# Every delete (an account, a proposal version) waits this long after it is asked for; only the coordinator can cancel it.
DELETION_DELAY = timedelta(days=7)
DELETION_DAYS = DELETION_DELAY.days


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
    # Part of every token's stamp (security.session_stamp); logging out bumps it, ending all of this person's sessions.
    session_epoch: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    role: Mapped[Role] = mapped_column(Enum(Role, name="role"))
    # Sign-ups start unapproved and cannot log in until the coordinator approves them.
    approved: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when the account's deletion is asked for (by the user or the coordinator).
    deletion_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the coordinator approves (or schedules it themselves): only then does the DELETION_DELAY clock start.
    deletion_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deletion_reason: Mapped[str | None] = mapped_column(Text)
    deletion_requested_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # Students only. The current thesis group (pending or active); faculty are linked from the thesis row instead.
    thesis_id: Mapped[int | None] = mapped_column(ForeignKey("theses.id", ondelete="SET NULL", use_alter=True, name="users_thesis_id_fkey"))
    # A frozen student asked the coordinator to restart at P1.
    restart_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The coordinator approved the restart; the next semester rollover puts them back at P1, fresh.
    restart_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    # post_update: users and theses point at each other, so this link is written in a second UPDATE.
    thesis = relationship("Thesis", foreign_keys=[thesis_id], post_update=True)

    @property
    def phase(self) -> Phase | None:
        """Students only: their thesis group's current phase. None without a live thesis, or once it is completed."""
        t = self.thesis
        return t.phase if t is not None and t.status.value in ("pending", "formed", "active") else None

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
        return self.deletion_requested_at is not None

    @property
    def deletion_executes_at(self) -> datetime | None:
        return self.deletion_approved_at and self.deletion_approved_at + DELETION_DELAY

    @property
    def deletion_by_coordinator(self) -> bool:
        return self.deletion_pending and self.deletion_requested_by_id != self.id
