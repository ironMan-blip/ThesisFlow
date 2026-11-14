import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, Phase
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, MilestoneOut, TimelineOut
from app.services import progress_service

DAY = timedelta(days=1)


def late_days(due_at: datetime, at: datetime) -> int:
    # Any part of a day after the due time counts as a full late day.
    return max(0, math.ceil((at - due_at) / DAY))


def _row(
    m: Milestone | None, phase: Phase, now: datetime, submitted_at: datetime | None, is_mine: bool, started_at: datetime
):
    if m is None:
        return MilestoneOut(
            phase=phase, due_at=None, grace_days=0, penalty_per_day=0, closes_at=None, status="not_set", mine=is_mine
        )
    closes_at = m.closes_at
    status = "open" if now <= m.due_at else "grace" if now <= closes_at else "closed"
    out = MilestoneOut(
        phase=phase,
        due_at=m.due_at,
        grace_days=m.grace_days,
        penalty_per_day=m.penalty_per_day,
        closes_at=closes_at,
        status=status,
        mine=is_mine,
    )
    if status == "open":
        out.countdown_to, out.countdown_label = m.due_at, "Due in"
    elif status == "grace":
        out.countdown_to, out.countdown_label = closes_at, "Grace ends in"
    # A phase that started after grace ended (late sign-up, restart) had nothing due: no personal status,
    # same rule as progress_service._missed.
    if is_mine and started_at < closes_at:
        out.submitted_at = submitted_at
        if submitted_at is None and now > closes_at:
            out.submission_status = "not_submitted"  # missed: no late count, the account freezes instead
        else:
            # Grace is the late window: days count from the due date, and keep counting until they submit.
            days = late_days(m.due_at, submitted_at or now)
            out.late_days = days
            out.penalty_percent = min(100, days * m.penalty_per_day)
            out.submission_status = "late" if days else "on_time" if submitted_at else "not_submitted"
    return out


def timeline(db: Session, user: User) -> TimelineOut:
    now = datetime.now(timezone.utc)
    milestones = {m.phase: m for m in db.scalars(select(Milestone))}
    # A student only has a submission for the phase they are in this semester.
    submitted = progress_service.submitted_at(db, user) if user.role == Role.student else None
    return TimelineOut(
        now=now,
        milestones=[
            _row(milestones.get(p), p, now, submitted, p == user.phase, user.phase_started_at) for p in Phase
        ],
        can_edit=user.role == Role.coordinator,
    )


def set_milestone(db: Session, phase: Phase, data: MilestoneIn) -> None:
    # No cross-phase order check: students in different phases have separate deadlines each semester.
    db.merge(Milestone(phase=phase, **data.model_dump()))
    db.commit()
