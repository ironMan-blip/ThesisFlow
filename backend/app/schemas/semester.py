from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

DHAKA = ZoneInfo("Asia/Dhaka")

StepKey = Literal["form_group", "pick_supervisor", "P1", "P2", "P3", "defense"]


def _parse_dhaka_local(value: str | None) -> datetime | None:
    if value is None or value == "":
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        raise ValueError("Provide Dhaka wall-clock time without a timezone offset")
    return dt.replace(tzinfo=DHAKA)


class SemesterCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    registration_opens_local: str | None = None
    registration_closes_local: str | None = None
    rollover: bool = False
    form_group_open: bool = True
    pick_supervisor_open: bool = True
    p1_open: bool = True
    p2_open: bool = True
    p3_open: bool = True
    defense_open: bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Semester name cannot be blank")
        return cleaned

    @property
    def registration_opens_at(self) -> datetime | None:
        return _parse_dhaka_local(self.registration_opens_local)

    @property
    def registration_closes_at(self) -> datetime | None:
        return _parse_dhaka_local(self.registration_closes_local)


class StepToggleIn(BaseModel):
    is_open: bool


class BulkStepsUpdateIn(BaseModel):
    form_group: bool | None = None
    pick_supervisor: bool | None = None
    P1: bool | None = None
    P2: bool | None = None
    P3: bool | None = None
    defense: bool | None = None


class StepStateOut(BaseModel):
    key: StepKey
    label: str
    description: str
    is_open: bool


class SemesterOut(BaseModel):
    id: int
    name: str
    started_at: datetime
    registration_opens_at: datetime | None
    registration_closes_at: datetime | None
    form_group_open: bool
    pick_supervisor_open: bool
    p1_open: bool
    p2_open: bool
    p3_open: bool
    defense_open: bool
    steps: list[StepStateOut]
    can_edit: bool = False
    rollover_summary: dict[str, int] | None = None