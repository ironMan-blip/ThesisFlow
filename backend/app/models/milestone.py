import enum
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Enum, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Phase(str, enum.Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Milestone(Base):
    """Deadline for one thesis phase, set by the coordinator. One row per phase."""

    __tablename__ = "milestones"

    phase: Mapped[Phase] = mapped_column(Enum(Phase, name="phase"), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    grace_minutes: Mapped[int] = mapped_column(Integer)
    penalty_per_day: Mapped[int] = mapped_column(Integer)  # percent of the phase mark

    @property
    def closes_at(self) -> datetime:
        # Uploads stop once the grace period after the due date ends.
        return self.due_at + timedelta(minutes=self.grace_minutes)
