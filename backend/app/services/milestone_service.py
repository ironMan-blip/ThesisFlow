import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.milestone import Milestone, Phase
from app.models.proposal import Proposal, ProposalVersion
from app.models.user import Role, User
from app.schemas.milestone import MilestoneIn, MilestoneOut, TimelineOut

DAY = timedelta(days=1)


def late_days(closes_at: datetime, at: datetime) -> int:
    # Any part of a day after the grace time counts as a full late day.
    return max(0, math.ceil((at - closes_at) / DAY))


def _row(m: Milestone | None, phase: Phase, now: datetime, submitted_at: datetime | None, is_student: bool):
    if m is None:
        return MilestoneOut(phase=phase, due_at=None, grace_minutes=0, penalty_per_day=0, closes_at=None, status="not_set")
    closes_at = m.due_at + timedelta(minutes=m.grace_minutes)
    status = "open" if now <= m.due_at else "grace" if now <= closes_at else "closed"
    out = MilestoneOut(
        phase=phase,
        due_at=m.due_at,
        grace_minutes=m.grace_minutes,
        penalty_per_day=m.penalty_per_day,
        closes_at=closes_at,
        status=status,
    )
    if is_student:
        # Not submitted yet: late days keep counting from now.
        days = late_days(closes_at, submitted_at or now)
        out.submitted_at = submitted_at
        out.late_days = days
        out.penalty_percent = min(100, days * m.penalty_per_day)
    return out


def timeline(db: Session, user: User, now: datetime | None = None) -> TimelineOut:
    now = now or datetime.now(timezone.utc)
    milestones = {m.phase: m for m in db.scalars(select(Milestone))}
    submitted = {}
    if user.role == Role.student:
        # The latest upload per phase is the one that counts, so a late re-upload is late.
        submitted = dict(
            db.execute(
                select(ProposalVersion.phase, func.max(ProposalVersion.created_at))
                .join(Proposal)
                .where(Proposal.owner_id == user.id)
                .group_by(ProposalVersion.phase)
            ).all()
        )
    return TimelineOut(
        now=now,
        milestones=[
            _row(milestones.get(p), p, now, submitted.get(p), user.role == Role.student) for p in Phase
        ],
    )


def set_milestone(db: Session, phase: Phase, data: MilestoneIn) -> None:
    db.merge(Milestone(phase=phase, **data.model_dump()))
    db.commit()
