from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Semester(Base):
    """One row per semester; the latest is the current one. A new row is added at each semester rollover."""

    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The P1 registration window runs for a week from here.
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
