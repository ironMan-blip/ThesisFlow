import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ThesisStatus(str, enum.Enum):
    pending = "pending"  # waiting for the supervisor to accept; no thesis ID yet
    active = "active"
    completed = "completed"
    dropped = "dropped"  # archived: the student restarted at P1 or left; versions are kept


class Thesis(Base):
    """A thesis group: one student, a supervisor and an optional co-supervisor. Every proposal version belongs to one."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SET NULL everywhere: deleting an account never deletes a thesis or its versions.
    student_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Null only on archived rows made from proposals that existed before thesis groups.
    supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    co_supervisor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    co_supervisor_accepted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[ThesisStatus] = mapped_column(
        Enum(ThesisStatus, name="thesis_status"), default=ThesisStatus.pending
    )
    # P3 deferrals by the coordinator (no panel yet): the second one freezes the student.
    deferrals: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # The coordinator's choice for this semester; applied at the semester rollover.
    defer_pending: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Registered for P1 this semester (only possible in the first week); cleared at every semester rollover.
    p1_registered: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    student = relationship("User", foreign_keys=[student_id])
    supervisor = relationship("User", foreign_keys=[supervisor_id])
    co_supervisor = relationship("User", foreign_keys=[co_supervisor_id])
    proposal = relationship("Proposal", back_populates="thesis", uselist=False)

    @property
    def versions(self) -> list:
        # Newest first; empty until the group's first upload makes its proposal.
        return self.proposal.versions if self.proposal else []

    @property
    def code(self) -> str | None:
        # The thesis ID people see; issued when the supervisor accepts.
        return None if self.status == ThesisStatus.pending else f"TH-{self.id:04d}"
