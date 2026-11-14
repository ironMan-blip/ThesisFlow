from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models.milestone import Phase
from app.models.thesis import ThesisStatus
from app.models.user import Role
from app.schemas.proposal import ProposalVersionOut


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    initials: str | None
    role: Role
    id_number: str
    email: str
    monogram: str


class ThesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str | None  # the thesis ID, e.g. TH-0007; None until the supervisor accepts
    status: ThesisStatus
    student: PersonOut | None  # None once the student's account is deleted
    supervisor: PersonOut | None
    co_supervisor: PersonOut | None
    co_supervisor_accepted: bool
    deferrals: int
    defer_pending: bool
    created_at: datetime


class ThesisDetailOut(ThesisOut):
    versions: list[ProposalVersionOut]  # newest first
    can_defer: bool = False  # coordinator only: P3 is submitted this semester


class SupervisionRequestOut(ThesisOut):
    slot: Literal["supervisor", "co_supervisor"]  # which role this faculty member is asked to take


class MyThesisOut(BaseModel):
    thesis: ThesisOut | None
    phase: Phase | None  # None once the thesis is completed
    frozen_reason: str | None
    restart_pending: bool
    restart_approved: bool  # they start fresh at P1 at the next semester rollover
    can_form_group: bool


class ThesisRequestIn(BaseModel):
    supervisor_id: int
    co_supervisor_id: int | None = None


class DeferIn(BaseModel):
    defer: bool
