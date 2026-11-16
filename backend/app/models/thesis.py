import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, false, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


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
    """A thesis group: one student, a supervisor and an optional co-supervisor. Every proposal version belongs to one."""

    __tablename__ = "theses"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The thesis ID people see, e.g. T12345678; issued when the group registers for P1.
    code: Mapped[str | None] = mapped_column(String(9), unique=True)
    # SET NULL everywhere: deleting an account never deletes a thesis or its versions.
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
    def co_supervisor_joined(self) -> bool:
        return self.co_supervisor_id is not None and self.co_supervisor_accepted and self.co_supervisor_approved

    def clear_co_supervisor(self) -> None:
        self.co_supervisor, self.co_supervisor_accepted, self.co_supervisor_approved = None, False, False

    @property
    def versions(self) -> list:
        # Newest first; empty until the group's first upload makes its proposal.
        return self.proposal.versions if self.proposal else []
