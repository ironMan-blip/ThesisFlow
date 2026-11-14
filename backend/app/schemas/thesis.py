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
    code: str | None  # the thesis ID, e.g. T12345678; None until the supervisor accepts
    status: ThesisStatus
    student: PersonOut | None  # None once the student's account is deleted
    supervisor: PersonOut | None
    co_supervisor: PersonOut | None
    co_supervisor_accepted: bool
    deferrals: int
    defer_pending: bool
    p1_registered: bool
    created_at: datetime


class ThesisDetailOut(ThesisOut):
    versions: list[ProposalVersionOut]  # newest first
    can_defer: bool = False  # coordinator only: can set (P3 submitted this semester) or undo a pending deferral


class SupervisionRequestOut(ThesisOut):
    slot: Literal["supervisor", "co_supervisor"]  # which role this faculty member is asked to take


class MyThesisOut(BaseModel):
    thesis: ThesisOut | None
    phase: Phase | None  # None once the thesis is completed
    frozen_reason: str | None
    restart_pending: bool
    restart_approved: bool  # they start fresh at P1 at the next semester rollover
    registration_closes_at: datetime | None  # end of this semester's one-week P1 registration
    registration_open: bool
    can_register: bool  # an accepted group in P1 that can register now
    can_form_group: bool
    can_cancel: bool  # the group request still waits for the supervisor
    show_deferral_warning: bool  # an active, unfrozen thesis deferred before: resubmit P3 or be frozen
    show_p1_registration: bool  # an active, unfrozen group in P1 sees its registration status


class ThesisRequestIn(BaseModel):
    supervisor_id: int
    co_supervisor_id: int | None = None


class DeferIn(BaseModel):
    defer: bool
