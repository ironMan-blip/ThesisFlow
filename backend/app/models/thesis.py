import enum
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.milestone import Phase


class ThesisStatus(str, enum.Enum):
    pending = "pending"  # waiting for the supervisor to accept
    formed = "formed"  # accepted by the supervisor; not registered for P1 yet, so no thesis ID and no uploads
    active = "active"  # registered for P1: has a thesis ID
    completed = "completed"
    dropped = "dropped"  # archived: the student restarted at P1 or left; versions are kept


# A group the supervisor accepted that is not completed or dropped.
FORMED = (ThesisStatus.formed, ThesisStatus.active)
# Never registered for P1, so no thesis ID and no versions: deleted, not archived, when the student leaves.
UNREGISTERED = (ThesisStatus.pending, ThesisStatus.formed)


class Thesis(Base):
    """A student group's thesis: its members, a supervisor and an optional co-supervisor. Every proposal version belongs
    to one. The members are the students whose users.thesis_id points here (see `members`)."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The thesis ID people see, e.g. T12345678; issued when the group registers for P1.
    code: Mapped[str | None] = mapped_column(String(9), unique=True)
    # The student group this thesis belongs to; null on theses made before groups, or once the group is gone.
    group_id: Mapped[int | None] = mapped_column(ForeignKey("student_groups.id", ondelete="SET NULL"), index=True)
    # SET NULL everywhere: deleting an account never deletes a thesis or its versions.
    # The member who sent the supervisor request (kept for the record; every member acts on the thesis).
    student_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    # Null only on archived rows made from proposals that existed before thesis groups.
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    co_supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    # A co-supervisor is only added to a formed group, and joins once both they (accepted) and the supervisor (approved) agree.
    co_supervisor_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    co_supervisor_approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[ThesisStatus] = mapped_column(
        Enum(ThesisStatus, name="thesis_status"), default=ThesisStatus.pending
    )
    # The group's phase: P1 from the start, moved on by progress_service.advance_phases at each new semester.
    phase: Mapped[Phase] = mapped_column(Enum(Phase, name="phase"), default=Phase.P1, server_default=Phase.P1.value)
    # When the current phase started (thesis made, new semester, or P3 again after a deferral); only uploads after it count.
    phase_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    # Set at the semester rollover when the group missed its deadline; members can then ask to restart.
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # P3 deferrals by the supervisor (panel members later): the second one cancels the thesis.
    deferrals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The coordinator's choice for this semester; applied at the semester rollover.
    defer_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Registered for P1 this semester (only possible in the first week); cleared at every semester rollover.
    p1_registered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by the first proposal upload; every later upload must use them. Changed only by an approved TitleChange.
    title: Mapped[str | None] = mapped_column(String(255))
    abstract: Mapped[str | None] = mapped_column(Text)

    student = relationship("User", foreign_keys=[student_id])
    group = relationship("Group")
    # Students currently on this thesis. Archived theses (restart, deleted accounts) may have none.
    members = relationship("User", primaryjoin="Thesis.id == foreign(User.thesis_id)", viewonly=True, order_by="User.id")
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    co_supervisor = relationship("User", foreign_keys=[co_supervisor_id])
    proposal = relationship("Proposal", back_populates="thesis", uselist=False)
    title_changes = relationship(
        "TitleChange", back_populates="thesis", order_by="TitleChange.id.desc()", passive_deletes=True
    )

    @property
    def co_supervisor_joined(self) -> bool:
        return self.co_supervisor_id is not None and self.co_supervisor_accepted and self.co_supervisor_approved

    def clear_co_supervisor(self) -> None:
        self.co_supervisor, self.co_supervisor_accepted, self.co_supervisor_approved = None, False, False

    @property
    def versions(self) -> list:
        # Newest first; empty until the group's first upload makes its proposal.
        return self.proposal.versions if self.proposal else []


# The supervisor has this long to accept a title and abstract change; after that the request lapses.
TITLE_CHANGE_WINDOW = timedelta(days=3)


class TitleChange(Base):
    """A group's request to change its thesis title and abstract. Only one can ever be approved per thesis."""

    __tablename__ = "title_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    abstract: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    # Set when the supervisor approves or rejects it; None while it waits (or after it lapsed).
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    thesis = relationship("Thesis", back_populates="title_changes")

    @property
    def expires_at(self) -> datetime:
        return self.created_at + TITLE_CHANGE_WINDOW

    @property
    def status(self) -> Literal["pending", "approved", "rejected", "expired"]:
        if self.decided_at is not None:
            return "approved" if self.approved else "rejected"
        return "pending" if datetime.now(timezone.utc) < self.expires_at else "expired"
