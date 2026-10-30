from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.models.milestone import Phase


class MilestoneIn(BaseModel):
    due_at: AwareDatetime
    grace_minutes: int = Field(ge=0, le=7 * 24 * 60)
    penalty_per_day: int = Field(ge=0, le=100)


class MilestoneOut(BaseModel):
    phase: Phase
    due_at: datetime | None  # None until the coordinator sets it
    grace_minutes: int
    penalty_per_day: int
    closes_at: datetime | None  # due_at + grace; late after this
    status: Literal["not_set", "open", "grace", "closed"]
    # Students only: their latest upload for this phase and what it costs them.
    submitted_at: datetime | None = None
    late_days: int | None = None
    penalty_percent: int | None = None


class TimelineOut(BaseModel):
    now: datetime  # server clock, so countdowns don't trust the browser's
    milestones: list[MilestoneOut]
