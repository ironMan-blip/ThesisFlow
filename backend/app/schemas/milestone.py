from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, computed_field

from app.models.milestone import Phase

MAX_GRACE_DAYS = 7
MAX_PENALTY_PER_DAY = 100
# The SRS shows and takes every time in Dhaka time. Bangladesh has no daylight saving, so the offset is fixed.
DHAKA = timezone(timedelta(hours=6))
DEFAULT_DUE_TIME = "23:59"  # a new deadline's time is end of day unless the coordinator changes it


class MilestoneIn(BaseModel):
    # Unknown fields are refused, so a client still sending due_at gets a 422 instead of a silently wrong deadline.
    model_config = ConfigDict(extra="forbid")

    # Dhaka wall-clock time as typed in the form, "YYYY-MM-DDTHH:MM"; no zone allowed.
    # Capped so adding grace days can't overflow past year 9999 (a 500).
    due_local: NaiveDatetime = Field(lt=datetime(9999, 12, 1))
    grace_days: int = Field(ge=0, le=MAX_GRACE_DAYS)
    penalty_per_day: int = Field(ge=0, le=MAX_PENALTY_PER_DAY)

    @property
    def due_at(self) -> datetime:
        return self.due_local.replace(tzinfo=DHAKA)


class MilestoneOut(BaseModel):
    phase: Phase
    due_at: datetime | None  # None until the coordinator sets it

    # due_at in Dhaka time, as the coordinator's date and time inputs hold it ("YYYY-MM-DD", "HH:MM").
    @computed_field
    @property
    def due_date(self) -> str | None:
        return self.due_at and self.due_at.astimezone(DHAKA).strftime("%Y-%m-%d")

    @computed_field
    @property
    def due_time(self) -> str:
        return self.due_at.astimezone(DHAKA).strftime("%H:%M") if self.due_at else DEFAULT_DUE_TIME

    grace_days: int
    penalty_per_day: int
    closes_at: datetime | None  # due_at + grace; late after this
    status: Literal["not_set", "open", "grace", "closed"]
    # What the live countdown ticks toward: due_at while open, closes_at in grace, else None.
    countdown_to: datetime | None = None
    countdown_label: str | None = None
    mine: bool = False  # students only: the phase they are in this semester
    # Students, for their own phase only: their latest upload and what it costs them.
    submitted_at: datetime | None = None
    late_days: int | None = None
    penalty_percent: int | None = None
    submission_status: Literal["not_submitted", "on_time", "late"] | None = None


class TimelineOut(BaseModel):
    now: datetime  # server clock, so countdowns don't trust the browser's
    milestones: list[MilestoneOut]
    can_edit: bool  # coordinator only
    registration_closes_at: datetime | None  # end of this semester's one-week P1 registration
    registration_open: bool
    # Input limits for the coordinator form, same values MilestoneIn enforces.
    max_grace_days: int = MAX_GRACE_DAYS
    max_penalty_per_day: int = MAX_PENALTY_PER_DAY
