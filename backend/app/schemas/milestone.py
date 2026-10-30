from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.models.milestone import Phase

MAX_GRACE_MINUTES = 7 * 24 * 60
MAX_PENALTY_PER_DAY = 100


class MilestoneIn(BaseModel):
    due_at: AwareDatetime
    grace_minutes: int = Field(ge=0, le=MAX_GRACE_MINUTES)
    penalty_per_day: int = Field(ge=0, le=MAX_PENALTY_PER_DAY)


class MilestoneOut(BaseModel):
    phase: Phase
    due_at: datetime | None  # None until the coordinator sets it
    grace_minutes: int
    penalty_per_day: int
    closes_at: datetime | None  # due_at + grace; late after this
    status: Literal["not_set", "open", "grace", "closed"]
    # What the live countdown ticks toward: due_at while open, closes_at in grace, else None.
    countdown_to: datetime | None = None
    countdown_label: str | None = None
    # Students only: their latest upload for this phase and what it costs them.
    submitted_at: datetime | None = None
    late_days: int | None = None
    penalty_percent: int | None = None
    submission_status: Literal["not_submitted", "on_time", "late"] | None = None


class TimelineOut(BaseModel):
    now: datetime  # server clock, so countdowns don't trust the browser's
    milestones: list[MilestoneOut]
    can_edit: bool  # coordinator only
    # Input limits for the coordinator form, same values MilestoneIn enforces.
    max_grace_minutes: int = MAX_GRACE_MINUTES
    max_penalty_per_day: int = MAX_PENALTY_PER_DAY
