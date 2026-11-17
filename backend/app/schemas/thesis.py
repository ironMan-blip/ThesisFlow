from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.milestone import Phase
from app.models.thesis import ThesisStatus
from app.models.user import Role
from app.schemas.proposal import ProposalVersionOut, TitleChangeOut, mark_versions


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
    student: PersonOut | None  # the member who sent the supervisor request; None once their account is deleted
    members: list[PersonOut]  # the group's students on this thesis now; may be empty once archived
    supervisor: PersonOut | None
    co_supervisor: PersonOut | None  # named on a formed group; a member once both flags below are true
    co_supervisor_accepted: bool  # by the co-supervisor
    co_supervisor_approved: bool  # by the supervisor
    co_supervisor_joined: bool  # both of the above: a member of the group
    deferrals: int
    defer_pending: bool
    p1_registered: bool
    created_at: datetime


class ThesisDetailOut(ThesisOut):
    versions: list[ProposalVersionOut]  # newest first
    title: str | None
    abstract: str | None
    title_change_request: TitleChangeOut | None = None  # a change waiting for the supervisor
    is_supervisor: bool = False  # the viewer is the supervisor (not the co-supervisor): decides title changes and deferral
    can_defer: bool = False  # supervisor only: can set (P3 submitted this semester) or undo a pending deferral

    @model_validator(mode="after")
    def _mark_versions(self):
        mark_versions(self.versions)
        return self


class SupervisionRequestOut(ThesisOut):
    # supervisor: form the group; co_supervisor: join it as co-supervisor; co_supervisor_approval: the supervisor
    # agrees to the co-supervisor the student added.
    slot: Literal["supervisor", "co_supervisor", "co_supervisor_approval"]


class MyThesisOut(BaseModel):
    thesis: ThesisOut | None
    phase: Phase | None  # None before P1 registration and once the thesis is completed
    frozen_reason: str | None
    restart_pending: bool
    restart_approved: bool  # they start fresh at P1 at the next semester rollover
    registration_opens_at: datetime | None  # this semester's P1 registration window, set by the coordinator
    registration_closes_at: datetime | None
    registration_open: bool
    registration_upcoming: bool  # the coordinator set it to open later this semester
    can_register: bool  # an accepted group in P1 that can register now
    register_block: str | None  # why an accepted P1 group can't register now
    can_form_group: bool  # a member of a ready group with no thesis can ask a supervisor
    form_group_block: str | None  # why not, while the student has no thesis
    can_cancel: bool  # the group request still waits for the supervisor
    can_add_co_supervisor: bool  # a formed group with no co-supervisor named
    can_cancel_co_supervisor: bool  # a co-supervisor was added but hasn't joined yet
    # Who the student can pick now: any faculty to form a group, anyone but the supervisor as co-supervisor, else none.
    faculty_choices: list[PersonOut]
    show_deferral_warning: bool  # an active, unfrozen thesis deferred before: resubmit P3 or be frozen
    show_p1_registration: bool  # an active, unfrozen group in P1 sees its registration status


class ThesisRequestIn(BaseModel):
    supervisor_id: int  # a group is formed with a supervisor only; a co-supervisor is added afterwards


class CoSupervisorIn(BaseModel):
    co_supervisor_id: int


class DeferIn(BaseModel):
    defer: bool
