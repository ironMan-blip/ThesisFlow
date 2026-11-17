from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Semester(Base):
    """One row per semester; the latest is the current one. A new row is added at each semester rollover."""

    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # P1 registration window, set by the coordinator (deadlines feature). Unset: one week from started_at.
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
