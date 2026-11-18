import enum
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Phase(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class MilestoneTemplate(Base):
    """Deadline for one thesis phase in one semester, set by the coordinator by hand. One row per phase and semester:
    a semester's deadlines fall in week 2 of the next one, so two semesters' deadlines for a phase run at once.
    Each group works to its own semester's deadline (Thesis.deadline_semester_id)."""

    __tablename__ = "milestone_templates"

    phase: Mapped[Phase] = mapped_column(Enum(Phase, name="phase"), primary_key=True)
    # Which semester's groups this deadline is for. The rollover neither waits for nor clears deadlines.
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_days: Mapped[int] = mapped_column(Integer)
    penalty_per_day: Mapped[int] = mapped_column(Integer)  # percent of the phase mark
    semester = relationship("Semester")

    @property
    def closes_at(self) -> datetime:
        # Uploads stop once the grace period after the due date ends.
        return self.due_at + timedelta(days=self.grace_days)


class GroupMilestone(Base):
    """One thesis group's milestone for its phase in one semester. Made on the group's first submission, or by
    progress_service.group_milestone(create=True) when an extension (F15) is granted before any submission."""

    __tablename__ = "group_milestones"
    __table_args__ = (UniqueConstraint("thesis_id", "semester_id", "phase"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    thesis_id: Mapped[int] = mapped_column(ForeignKey("theses.id", ondelete="CASCADE"))
    semester_id: Mapped[int] = mapped_column(ForeignKey("semesters.id", ondelete="CASCADE"))
    phase: Mapped[Phase] = mapped_column(Enum(Phase, name="phase"))
    # Set by an approved deadline extension (F15); replaces the template's due date for this group.
    extended_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Upload time of the deliverable; None when nothing is submitted.
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deliverable = relationship("Deliverable", back_populates="group_milestone", uselist=False, passive_deletes=True)

    def effective_due_at(self, template: MilestoneTemplate) -> datetime:
        # An extension only adds time: if the coordinator later moves the deadline past it, the later date wins.
        return max(self.extended_due_at, template.due_at) if self.extended_due_at else template.due_at


class Deliverable(Base):
    """The version a group submitted for a milestone: its latest upload for that phase. Final once grace ends."""

    __tablename__ = "deliverables"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_milestone_id: Mapped[int] = mapped_column(ForeignKey("group_milestones.id", ondelete="CASCADE"), unique=True)
    proposal_version_id: Mapped[int] = mapped_column(ForeignKey("proposal_versions.id", ondelete="CASCADE"), unique=True)

    group_milestone: Mapped[GroupMilestone] = relationship(back_populates="deliverable")
    proposal_version = relationship("ProposalVersion")
