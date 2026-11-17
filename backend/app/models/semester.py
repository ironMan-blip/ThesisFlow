from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.milestone import Phase


class Semester(Base):
    __tablename__ = "semesters"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), server_default="Current Semester", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    registration_opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    registration_closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # F1: Open/close state for every step in the thesis lifecycle
    form_group_open: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True, nullable=False)
    pick_supervisor_open: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True, nullable=False)
    p1_open: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True, nullable=False)
    p2_open: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True, nullable=False)
    p3_open: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True, nullable=False)
    defense_open: Mapped[bool] = mapped_column(Boolean, server_default="false", default=False, nullable=False)

    def is_phase_open(self, phase: Phase) -> bool:
        return {
            Phase.P1: self.p1_open,
            Phase.P2: self.p2_open,
            Phase.P3: self.p3_open,
        }[phase]