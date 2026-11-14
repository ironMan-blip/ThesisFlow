"""Student phase rules: one phase per semester, P1 -> P2 -> P3.

- Groups can be formed and accepted any time, but an accepted group can only register for P1 in the first week
  of each semester. A P1 student whose group didn't register has nothing due and waits for the next semester.
- Uploading for the current phase before its grace period ends counts as submitted (late or not).
- Grace ends with no upload: the student is frozen and can ask the coordinator to restart at P1 at any time.
  An approved restart starts fresh at P1 at the next semester rollover.
- After P3 the coordinator may defer the thesis: once means P3 again next semester, twice freezes the student.
- The semester rollover moves everyone on and clears the deadlines for the next semester.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.milestone import Deliverable, GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import ProposalVersion
from app.models.semester import Semester
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User

NEXT_PHASE = {Phase.P1: Phase.P2, Phase.P2: Phase.P3}
MAX_DEFERRALS = 2  # the second deferral freezes the student
REGISTRATION_WINDOW = timedelta(weeks=1)


@dataclass
class Standing:
    """Where a student stands in their current phase this semester."""

    template: MilestoneTemplate | None  # this semester's deadline for their phase
    group_milestone: GroupMilestone | None  # their group's own milestone this semester; None until they submit
    frozen_reason: str | None = None  # set when the account is frozen

    @property
    def frozen(self) -> bool:
        return self.frozen_reason is not None

    @property
    def submitted_at(self) -> datetime | None:
        # Latest upload that counts for their phase; a late re-upload is late.
        return self.group_milestone and self.group_milestone.submitted_at

    @property
    def due_at(self) -> datetime | None:
        # An approved extension moves only this group's due date.
        if self.template is None:
            return None
        return self.group_milestone.effective_due_at(self.template) if self.group_milestone else self.template.due_at

    @property
    def closes_at(self) -> datetime | None:
        return self.due_at and self.due_at + timedelta(days=self.template.grace_days)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def registration_closes_at(db: Session) -> datetime | None:
    # The latest semester is the current one; the migration creates the first.
    started = db.scalar(select(func.max(Semester.started_at)))
    return started and started + REGISTRATION_WINDOW


def registration_open(db: Session) -> bool:
    closes = registration_closes_at(db)
    return closes is not None and _now() <= closes


def current_semester_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Semester.id)))


def group_milestone(db: Session, user: User, create: bool = False) -> GroupMilestone | None:
    """The student's group milestone for their current phase this semester. Earlier semesters (a deferred P3) don't count."""
    if user.thesis_id is None or user.phase is None:
        return None
    key = dict(thesis_id=user.thesis_id, semester_id=current_semester_id(db), phase=user.phase)
    gm = db.scalar(select(GroupMilestone).filter_by(**key))
    if gm is None and create:
        gm = GroupMilestone(**key)
        db.add(gm)
        db.flush()
    return gm


def phase_uploads(user: User):
    """Filter for the uploads that count toward the student's group milestone: this phase, since it started."""
    return (
        ProposalVersion.proposal.has(thesis_id=user.thesis_id)
        & (ProposalVersion.phase == user.phase)
        & (ProposalVersion.created_at >= user.phase_started_at)
    )


def sync_deliverable(db: Session, gm: GroupMilestone, user: User) -> None:
    # The deliverable is the latest upload for the phase; call after adding or removing one.
    db.flush()
    latest = db.scalar(
        select(ProposalVersion)
        .where(phase_uploads(user))
        .order_by(ProposalVersion.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)  # a re-submit bumps created_at with a bulk UPDATE
    )
    db.execute(delete(Deliverable).where(Deliverable.group_milestone_id == gm.id))
    if latest is not None:
        db.add(Deliverable(group_milestone_id=gm.id, proposal_version_id=latest.id))
    gm.submitted_at = latest and latest.created_at
    db.flush()
    db.expire(gm, ["deliverable"])


def submitted_at(db: Session, user: User) -> datetime | None:
    gm = group_milestone(db, user)
    return gm and gm.submitted_at


def held_to(user: User, closes_at: datetime) -> bool:
    # Only students who could upload have anything due: their phase started before the deadline closed, their
    # group is accepted and, in P1, registered this semester. Everyone else waits for next semester.
    thesis = user.thesis
    return (
        user.phase_started_at < closes_at
        and thesis is not None
        and thesis.status == ThesisStatus.active
        and (user.phase != Phase.P1 or thesis.p1_registered)
    )


def _missed(user: User, s: Standing, now: datetime) -> bool:
    return s.closes_at is not None and now > s.closes_at and s.submitted_at is None and held_to(user, s.closes_at)


def standing(db: Session, user: User, now: datetime | None = None) -> Standing:
    now = now or _now()
    s = Standing(db.get(MilestoneTemplate, user.phase) if user.phase else None, group_milestone(db, user))
    reason = None
    if user.frozen_at is not None:
        thesis = user.thesis
        deferred = thesis is not None and thesis.deferrals >= MAX_DEFERRALS
        reason = "Your thesis was deferred twice" if deferred else f"You missed the {user.phase.value} deadline"
    elif user.phase and _missed(user, s, now):
        # Shown as soon as grace ends; saved at the rollover. A deadline extension lifts it before then.
        reason = f"You missed the {user.phase.value} deadline"
    elif user.restart_pending or user.restart_approved:
        # Asking for a fresh start is final: a later deadline extension doesn't reopen this thesis.
        reason = "You asked to restart at P1"
    s.frozen_reason = reason
    return s


def _students(db: Session):
    return db.scalars(
        select(User).where(User.role == Role.student, User.approved.is_(True)).with_for_update()
    )


def next_semester(db: Session) -> dict[str, int]:
    """Coordinator: end the semester. Moves students on, applies P3 deferrals, saves freezes and clears the deadlines."""
    now = _now()
    templates = {t.phase: t for t in db.scalars(select(MilestoneTemplate).with_for_update())}
    extended = db.scalars(
        select(GroupMilestone).where(
            GroupMilestone.semester_id == current_semester_id(db), GroupMilestone.extended_due_at.is_not(None)
        )
    )
    still_open = {t.phase.value for t in templates.values() if now <= t.closes_at}
    # A group with an extension can still upload after the phase's own grace ends.
    still_open |= {g.phase.value for g in extended if g.phase in templates and now <= Standing(templates[g.phase], g).closes_at}
    if still_open:
        # Moving on now would cut off students who can still upload.
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{', '.join(sorted(still_open))} is still open, wait until its grace period ends"
        )
    result = {"advanced": 0, "completed": 0, "deferred": 0, "frozen": 0, "restarted": 0}
    for user in _students(db):
        if user.restart_approved:
            _restart(db, user, now)
            result["restarted"] += 1
            continue
        if user.phase is None or user.frozen_at is not None:
            continue
        s = standing(db, user, now)
        thesis = user.thesis
        if s.frozen:
            user.frozen_at = now
            result["frozen"] += 1
        elif s.submitted_at is None or thesis is None or thesis.status != ThesisStatus.active:
            continue  # nothing due for them this semester (no deadline, or they started late): same phase again
        elif user.phase in NEXT_PHASE:
            user.phase, user.phase_started_at = NEXT_PHASE[user.phase], now
            result["advanced"] += 1
        elif thesis.defer_pending:
            thesis.defer_pending = False
            thesis.deferrals += 1
            if thesis.deferrals >= MAX_DEFERRALS:
                user.frozen_at = now
                result["frozen"] += 1
            else:
                user.phase_started_at = now  # P3 again; last semester's upload no longer counts
                result["deferred"] += 1
        else:
            thesis.status, user.phase = ThesisStatus.completed, None
            result["completed"] += 1
    db.execute(delete(MilestoneTemplate))
    db.execute(update(Thesis).values(p1_registered=False))  # P1 registration is per semester
    db.add(Semester(started_at=now))  # opens P1 registration for the new semester
    db.commit()
    return result


def can_register(db: Session, user: User) -> bool:
    thesis = user.thesis
    return (
        user.phase == Phase.P1
        and thesis is not None
        and thesis.status == ThesisStatus.active
        and not thesis.p1_registered
        and not standing(db, user).frozen
        and registration_open(db)
    )


def register_p1(db: Session, user: User) -> None:
    """Student: register their accepted group for P1 this semester. Only in the first week of the semester."""
    user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if not can_register(db, user):
        if not registration_open(db):
            raise HTTPException(status.HTTP_409_CONFLICT, "P1 registration is closed, register in the first week of next semester")
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a P1 student with an accepted thesis group can register, once per semester")
    user.thesis.p1_registered = True
    db.commit()


def can_defer(db: Session, thesis: Thesis) -> bool:
    student = thesis.student
    return (
        thesis.status == ThesisStatus.active
        and student is not None
        and student.phase == Phase.P3
        and not standing(db, student).frozen
        and submitted_at(db, student) is not None
    )


def set_defer(db: Session, thesis_id: int, defer: bool) -> Thesis:
    """Coordinator: defer (or undo deferring) a thesis whose P3 is submitted. Takes effect at the rollover."""
    thesis = db.scalar(select(Thesis).where(Thesis.id == thesis_id).with_for_update())
    if thesis is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thesis with that id")
    if defer and not can_defer(db, thesis):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an active thesis with P3 submitted this semester can be deferred")
    thesis.defer_pending = defer
    db.commit()
    db.refresh(thesis)
    return thesis


def request_restart(db: Session, user: User) -> User:
    # Any time while frozen; an approved restart starts at the next semester rollover.
    if user.role != Role.student or not standing(db, user).frozen:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a frozen student account can ask to restart at P1")
    if user.restart_approved:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restart already approved, you start at P1 next semester")
    if user.restart_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Restart already requested, waiting for the coordinator")
    user.restart_requested_at = _now()
    db.commit()
    db.refresh(user)
    return user


def _restarts():
    return select(User).where(User.restart_requested_at.is_not(None))


def pending_restarts(db: Session) -> list[User]:
    return list(db.scalars(_restarts().order_by(User.restart_requested_at)))


def count_restarts(db: Session) -> int:
    return db.scalar(_restarts().with_only_columns(func.count()))


def _restart_pending(db: Session, user_id: int) -> User:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if user is None or not user.restart_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending restart request with that id")
    return user


def approve_restart(db: Session, user_id: int) -> User:
    """Takes effect at the next semester rollover, see _restart."""
    user = _restart_pending(db, user_id)
    user.restart_requested_at, user.restart_approved = None, True
    db.commit()
    db.refresh(user)
    return user


def _restart(db: Session, user: User, now: datetime) -> None:
    """Fresh start at P1 with no thesis. The old thesis is archived with all its versions; the next group gets a new thesis ID."""
    thesis, user.thesis = user.thesis, None
    if thesis is not None and thesis.status == ThesisStatus.pending:
        db.delete(thesis)  # never accepted, so it has no thesis ID and no versions
    elif thesis is not None:
        thesis.status, thesis.defer_pending = ThesisStatus.dropped, False
    user.phase, user.phase_started_at = Phase.P1, now
    user.frozen_at, user.restart_approved = None, False


def reject_restart(db: Session, user_id: int) -> User:
    user = _restart_pending(db, user_id)
    user.restart_requested_at = None
    db.commit()
    db.refresh(user)
    return user
