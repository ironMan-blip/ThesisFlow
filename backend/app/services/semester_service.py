from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import Phase
from app.models.semester import Semester
from app.models.user import Role, User
from app.schemas.semester import (
    BulkStepsUpdateIn,
    SemesterCreateIn,
    SemesterOut,
    StepKey,
    StepStateOut,
)
from app.services import progress_service

STEP_METADATA: list[tuple[StepKey, str, str, str]] = [
    ("form_group", "form_group_open", "Form Group", "Students can create groups, send invitations, and join or leave teams."),
    ("pick_supervisor", "pick_supervisor_open", "Pick Supervisor", "Groups can request supervisors and add co-supervisors."),
    ("P1", "p1_open", "Pre-Thesis 1 (P1)", "P1 registration and P1 proposal submissions are active."),
    ("P2", "p2_open", "Pre-Thesis 2 (P2)", "P2 progress report uploads and submissions are active."),
    ("P3", "p3_open", "Final Thesis (P3)", "P3 final report uploads and submissions are active."),
    ("defense", "defense_open", "Final Defense", "Defense scheduling and final defense evaluations are active."),
]

STEP_TO_ATTR: dict[StepKey, str] = {key: attr for key, attr, _, _ in STEP_METADATA}


def get_active_semester(db: Session) -> Semester:
    return progress_service.ensure_semester(db)


def list_semesters(db: Session) -> list[Semester]:
    return list(db.scalars(select(Semester).order_by(Semester.id.desc())))


def serialize_semester(
    semester: Semester,
    user: User | None = None,
    rollover_summary: dict[str, int] | None = None,
) -> SemesterOut:
    opens, closes = (
        (semester.registration_opens_at, semester.registration_closes_at)
        if semester.registration_opens_at and semester.registration_closes_at
        else (semester.started_at, semester.started_at + progress_service.REGISTRATION_WINDOW)
    )
    steps = [
        StepStateOut(
            key=key,
            label=label,
            description=desc,
            is_open=bool(getattr(semester, attr)),
        )
        for key, attr, label, desc in STEP_METADATA
    ]
    return SemesterOut(
        id=semester.id,
        name=semester.name,
        started_at=semester.started_at,
        registration_opens_at=opens,
        registration_closes_at=closes,
        form_group_open=semester.form_group_open,
        pick_supervisor_open=semester.pick_supervisor_open,
        p1_open=semester.p1_open,
        p2_open=semester.p2_open,
        p3_open=semester.p3_open,
        defense_open=semester.defense_open,
        steps=steps,
        can_edit=bool(user and user.role == Role.coordinator),
        rollover_summary=rollover_summary,
    )


def create_semester(db: Session, data: SemesterCreateIn) -> tuple[Semester, dict[str, int] | None]:
    opens_at = data.registration_opens_at
    closes_at = data.registration_closes_at

    if (opens_at is None) != (closes_at is None):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Provide both P1 registration open and close times, or leave both blank",
        )
    if opens_at and closes_at and closes_at <= opens_at:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "P1 registration must close after it opens",
        )

    # Always the rollover: a new semester without it would leave every group's submissions on the old semester's
    # milestones (as if nothing was handed in) and keep last semester's P1 registrations.
    rollover_summary = progress_service.next_semester(db)
    semester = get_active_semester(db)
    semester.name = data.name

    semester.registration_opens_at = opens_at
    semester.registration_closes_at = closes_at
    semester.form_group_open = data.form_group_open
    semester.pick_supervisor_open = data.pick_supervisor_open
    semester.p1_open = data.p1_open
    semester.p2_open = data.p2_open
    semester.p3_open = data.p3_open
    semester.defense_open = data.defense_open

    db.commit()
    db.refresh(semester)
    return semester, rollover_summary


def set_step(db: Session, step: StepKey, is_open: bool) -> Semester:
    semester = get_active_semester(db)
    attr = STEP_TO_ATTR[step]
    setattr(semester, attr, is_open)
    db.commit()
    db.refresh(semester)
    return semester


def update_steps(db: Session, data: BulkStepsUpdateIn) -> Semester:
    semester = get_active_semester(db)
    updates = data.model_dump(exclude_none=True)
    for step_key, val in updates.items():
        setattr(semester, STEP_TO_ATTR[step_key], val)  # type: ignore[index]
    db.commit()
    db.refresh(semester)
    return semester


def is_step_open(db: Session, step: StepKey) -> bool:
    semester = progress_service.current_semester(db)
    if semester is None:
        return True
    return bool(getattr(semester, STEP_TO_ATTR[step]))


def is_phase_open(db: Session, phase: Phase) -> bool:
    semester = progress_service.current_semester(db)
    if semester is None:
        return True
    return semester.is_phase_open(phase)


def require_step_open(db: Session, step: StepKey) -> None:
    if not is_step_open(db, step):
        labels = {key: label for key, _, label, _ in STEP_METADATA}
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{labels[step]} is currently closed by the coordinator",
        )