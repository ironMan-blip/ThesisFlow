import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import MilestoneTemplate, Phase
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, MilestoneOut, TimelineOut
from app.services import progress_service

DAY = timedelta(days=1)


def late_days(due_at: datetime, at: datetime) -> int:
    # Any part of a day after the due time counts as a full late day.
    return max(0, math.ceil((at - due_at) / DAY))


def _row(m: MilestoneTemplate | None, phase: Phase, now: datetime, mine: progress_service.Standing | None, user: User):
    # mine: the student's standing when this is their phase; their group's due date may be extended.
    is_mine = mine is not None
    if m is None:
        return MilestoneOut(
            phase=phase, due_at=None, grace_days=0, penalty_per_day=0, closes_at=None, status="not_set", mine=is_mine
        )
    due_at, closes_at = (mine.due_at, mine.closes_at) if mine else (m.due_at, m.closes_at)
    status = "open" if now <= due_at else "grace" if now <= closes_at else "closed"
    out = MilestoneOut(
        phase=phase,
        due_at=due_at,
        grace_days=m.grace_days,
        penalty_per_day=m.penalty_per_day,
        closes_at=closes_at,
        status=status,
        mine=is_mine,
    )
    if status == "open":
        out.countdown_to, out.countdown_label = due_at, "Due in"
    elif status == "grace":
        out.countdown_to, out.countdown_label = closes_at, "Grace ends in"
    # A student who couldn't upload (phase started after grace ended, or no accepted group) had nothing due:
    # no personal status, same rule as progress_service._missed.
    if mine and progress_service.held_to(user, closes_at):
        submitted_at = mine.submitted_at
        out.submitted_at = submitted_at
        if submitted_at is None and now > closes_at:
            out.submission_status = "not_submitted"  # missed: no late count, the account freezes instead
        else:
            # Grace is the late window: days count from the due date, and keep counting until they submit.
            days = late_days(due_at, submitted_at or now)
            out.late_days = days
            out.penalty_percent = min(100, days * m.penalty_per_day)
            out.submission_status = "late" if days else "on_time" if submitted_at else "not_submitted"
    return out


def timeline(db: Session, user: User) -> TimelineOut:
    now = datetime.now(timezone.utc)
    templates = {m.phase: m for m in db.scalars(select(MilestoneTemplate))}
    # A student only has a submission for the phase they are in this semester.
    mine = progress_service.standing(db, user, now) if user.role == Role.student and user.phase else None
    return TimelineOut(
        now=now,
        milestones=[_row(templates.get(p), p, now, mine if p == user.phase else None, user) for p in Phase],
        can_edit=user.role == Role.coordinator,
        registration_closes_at=progress_service.registration_closes_at(db),
        registration_open=progress_service.registration_open(db),
    )


def set_milestone(db: Session, phase: Phase, data: MilestoneIn) -> None:
    # No cross-phase order check: students in different phases have separate deadlines each semester.
    if data.due_at + timedelta(days=data.grace_days) <= datetime.now(timezone.utc):
        # A deadline that is already over would count everyone in the phase as missing it.
        raise HTTPException(422, "The deadline and grace period must end in the future")
    registration_closes = progress_service.registration_closes_at(db)
    if phase == Phase.P1 and registration_closes and data.due_at <= registration_closes:
        # Groups can still register until then, so an earlier P1 deadline would catch them mid-registration.
        raise HTTPException(422, "P1 can't be due before P1 registration closes")
    db.merge(MilestoneTemplate(phase=phase, **data.model_dump()))
    db.commit()
