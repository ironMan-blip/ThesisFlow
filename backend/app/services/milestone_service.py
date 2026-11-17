import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import MilestoneTemplate, Phase
from app.models.semester import Semester
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, MilestoneOut, RegistrationIn, TimelineOut
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
        semester_id=m.semester_id,
        semester_name=m.semester and m.semester.name,
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
    if mine and progress_service.held_to(user.thesis, closes_at):
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


def timeline(db: Session, user: User, semester_id: int | None = None) -> TimelineOut:
    """semester_id: whose deadlines to show, for the coordinator (default: the current semester's)."""
    now = datetime.now(timezone.utc)
    shown = (user.role == Role.coordinator and semester_id) or progress_service.current_semester_id(db)
    templates = {m.phase: m for m in db.scalars(select(MilestoneTemplate).where(MilestoneTemplate.semester_id == shown))}
    # A student only has a submission for the phase they are in, held to their own group's deadline semester.
    mine = progress_service.standing(db, user, now) if user.role == Role.student and user.phase else None
    opens, closes = progress_service.registration_window(db) or (None, None)
    return TimelineOut(
        now=now,
        milestones=[
            _row(mine.template, p, now, mine, user) if mine and p == user.phase else _row(templates.get(p), p, now, None, user)
            for p in Phase
        ],
        semester_id=shown,
        can_edit=user.role == Role.coordinator,
        semesters=list(db.scalars(select(Semester).order_by(Semester.id.desc()))) if user.role == Role.coordinator else [],
        registration_opens_at=opens,
        registration_closes_at=closes,
        registration_open=opens is not None and opens <= now <= closes,
    )


def set_registration(db: Session, data: RegistrationIn) -> None:
    """Coordinator: this semester's P1 registration window. Groups already registered stay registered."""
    if data.closes_at <= data.opens_at:
        raise HTTPException(422, "P1 registration must close after it opens")
    semester = progress_service.ensure_semester(db)
    p1 = db.get(MilestoneTemplate, (Phase.P1, semester.id))
    if p1 and p1.due_at <= data.closes_at:
        # Same rule as set_milestone, from the other side.
        raise HTTPException(422, "P1 registration must close before P1 is due")
    semester.registration_opens_at, semester.registration_closes_at = data.opens_at, data.closes_at
    db.commit()


def set_milestone(db: Session, phase: Phase, data: MilestoneIn) -> None:
    # No cross-phase order check: students in different phases have separate deadlines each semester.
    # One deadline per phase and semester: editing another semester's leaves this one alone.
    now = datetime.now(timezone.utc)
    semester = db.get(Semester, data.semester_id)
    if semester is None:
        raise HTTPException(422, "Pick the semester this deadline is for")
    current = db.get(MilestoneTemplate, (phase, semester.id))
    due_at = data.due_at
    if current and current.due_at.replace(second=0, microsecond=0) == due_at.replace(second=0, microsecond=0):
        # The form only sends whole minutes, so the same minute means "keep this due date", even one set with seconds.
        due_at = current.due_at
    if due_at + timedelta(days=data.grace_days) <= now:
        # A deadline that is already over would count everyone in the phase as missing it.
        raise HTTPException(422, "The deadline and grace period must end in the future")
    if due_at <= now and (current is None or current.due_at != due_at):
        # A new due date in the past makes everyone late at once. Keeping a passed due date (to change grace or
        # penalty during grace) is fine.
        raise HTTPException(422, "The due date must be in the future")
    if current and due_at <= now and data.penalty_per_day > current.penalty_per_day:
        # Penalties are worked out from the current rate, so raising it after the due date would make work already
        # handed in late cost more. Before the due date nobody is late yet; lowering it only helps students.
        raise HTTPException(422, "The due date has passed, so the late penalty can only be lowered now")
    registration_closes = progress_service.semester_registration_window(semester)[1]
    if phase == Phase.P1 and due_at <= registration_closes:
        # Groups can still register until then, so an earlier P1 deadline would catch them mid-registration.
        raise HTTPException(422, f"P1 can't be due before {semester.name}'s P1 registration closes")
    db.merge(MilestoneTemplate(
        phase=phase, due_at=due_at, grace_days=data.grace_days, penalty_per_day=data.penalty_per_day,
        semester_id=semester.id,
    ))
    db.commit()
