from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, computed_field

from app.models.milestone import Phase

MAX_GRACE_DAYS = 7
MAX_PENALTY_PER_DAY = 100
# The SRS shows and takes every time in Dhaka time. Bangladesh has no daylight saving, so the offset is fixed.
DHAKA = timezone(timedelta(hours=6))
DEFAULT_DUE_TIME = "23:59"  # a new deadline's time is end of day unless the coordinator changes it
# Lower bound: 0001-01-01 in Dhaka is 1 BC in UTC; Postgres stores it but psycopg can't read it back, breaking every page.
EARLIEST = datetime(2000, 1, 1)


class MilestoneIn(BaseModel):
    # Unknown fields are refused, so a client still sending due_at gets a 422 instead of a silently wrong deadline.
    model_config = ConfigDict(extra="forbid")

    # Dhaka wall-clock time as typed in the form, "YYYY-MM-DDTHH:MM"; no zone allowed.
    # Capped so adding grace days can't overflow past year 9999 (a 500).
    due_local: NaiveDatetime = Field(lt=datetime(9999, 12, 1))
    grace_days: int = Field(ge=0, le=MAX_GRACE_DAYS)
    penalty_per_day: int = Field(ge=0, le=MAX_PENALTY_PER_DAY)
    semester_id: int  # the semester whose groups this deadline is for (checked to exist by the service)

    @property
    def due_at(self) -> datetime:
        return self.due_local.replace(tzinfo=DHAKA)


def _local(at: datetime | None) -> str | None:
    # As a datetime-local input holds it, in Dhaka time ("YYYY-MM-DDTHH:MM").
    return at and at.astimezone(DHAKA).strftime("%Y-%m-%dT%H:%M")


class RegistrationIn(BaseModel):
    """The P1 registration window, in Dhaka wall-clock time like MilestoneIn."""

    model_config = ConfigDict(extra="forbid")

    opens_local: NaiveDatetime = Field(ge=EARLIEST, lt=datetime(9999, 12, 1))
    closes_local: NaiveDatetime = Field(ge=EARLIEST, lt=datetime(9999, 12, 1))
    semester_id: int  # the semester whose P1 registration this is (checked to exist by the service)

    @property
    def opens_at(self) -> datetime:
        return self.opens_local.replace(tzinfo=DHAKA)

    @property
    def closes_at(self) -> datetime:
        return self.closes_local.replace(tzinfo=DHAKA)


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
    semester_id: int | None = None  # the semester this deadline is for; None until set
    semester_name: str | None = None
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


class SemesterTagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class TimelineOut(BaseModel):
    now: datetime  # server clock, so countdowns don't trust the browser's
    milestones: list[MilestoneOut]
    semester_id: int | None = None  # whose deadlines are shown (a student's own phase row is their group's semester)
    can_edit: bool  # coordinator only
    semesters: list[SemesterTagOut] = []  # coordinator only, newest (current) first: the tags a deadline can take
    current_semester_id: int | None = None
    registration_opens_at: datetime | None  # the shown semester's P1 registration window
    registration_closes_at: datetime | None
    registration_open: bool

    # The dashboard's "up next": the student's own running phase, else the countdown that ends soonest.
    @computed_field
    @property
    def next_deadline(self) -> MilestoneOut | None:
        running = [m for m in self.milestones if m.countdown_to]
        return next((m for m in running if m.mine), None) or min(running, key=lambda m: m.countdown_to, default=None)

    @computed_field
    @property
    def registration_status(self) -> Literal["not_set", "upcoming", "open", "closed"]:
        if self.registration_opens_at is None:
            return "not_set"
        return "open" if self.registration_open else "upcoming" if self.now < self.registration_opens_at else "closed"

    # The window as the coordinator's datetime-local inputs hold it.
    @computed_field
    @property
    def registration_opens_local(self) -> str | None:
        return _local(self.registration_opens_at)

    @computed_field
    @property
    def registration_closes_local(self) -> str | None:
        return _local(self.registration_closes_at)

    # Input limits for the coordinator form, same values MilestoneIn enforces.
    max_grace_days: int = MAX_GRACE_DAYS
    max_penalty_per_day: int = MAX_PENALTY_PER_DAY
