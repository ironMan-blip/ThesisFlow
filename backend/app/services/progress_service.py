"""Phase rules (deadlines feature). The phase belongs to the thesis group, one phase per semester, P1 -> P2 -> P3.

- Groups can be formed and accepted any time, but an accepted group can only register for P1 in the first week
  of each semester. A P1 group that didn't register has nothing due and waits for the next semester.
- Uploading for the group's phase before its grace period ends counts as submitted (late or not).
- Grace ends with no upload: the group is frozen, and its members can ask the coordinator to restart at P1.
  An approved restart starts that student fresh (no group, no thesis) at the next semester rollover.
- After P3 the supervisor may defer the thesis: once means P3 again next semester, twice cancels the thesis.
- The semester rollover (semester feature) calls advance_phases to move every group on, then clears the deadlines.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.group import MIN_MEMBERS
from app.models.milestone import Deliverable, GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import ProposalVersion
from app.models.semester import Semester
from app.models.thesis import FORMED, UNREGISTERED, Thesis, ThesisStatus
from app.models.user import Role, User

NEXT_PHASE = {Phase.P1: Phase.P2, Phase.P2: Phase.P3}
MAX_DEFERRALS = 2  # the second deferral cancels the thesis
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


def current_semester(db: Session) -> Semester | None:
    # The latest semester is the current one; the migration creates the first.
    return db.scalar(select(Semester).order_by(Semester.id.desc()).limit(1))


def registration_window(db: Session) -> tuple[datetime, datetime] | None:
    """(opens, closes) of this semester's P1 registration: the coordinator's dates, else one week from its start."""
    s = current_semester(db)
    if s is None:
        return None
    if s.registration_opens_at and s.registration_closes_at:
        return s.registration_opens_at, s.registration_closes_at
    return s.started_at, s.started_at + REGISTRATION_WINDOW


def registration_opens_at(db: Session) -> datetime | None:
    window = registration_window(db)
    return window and window[0]


def registration_closes_at(db: Session) -> datetime | None:
    window = registration_window(db)
    return window and window[1]


def registration_open(db: Session) -> bool:
    window = registration_window(db)
    return window is not None and window[0] <= _now() <= window[1]


def registration_upcoming(db: Session) -> bool:
    window = registration_window(db)
    return window is not None and _now() < window[0]


def current_semester_id(db: Session) -> int | None:
    return db.scalar(select(func.max(Semester.id)))


def group_milestone(db: Session, user: User, create: bool = False) -> GroupMilestone | None:
    """The student's group milestone for its current phase this semester. Earlier semesters (a deferred P3) don't count."""
    return _milestone(db, user.thesis, create) if user.phase else None


def _milestone(db: Session, thesis: Thesis, create: bool = False) -> GroupMilestone | None:
    key = dict(thesis_id=thesis.id, semester_id=current_semester_id(db), phase=thesis.phase)
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
        & (ProposalVersion.created_at >= user.thesis.phase_started_at)
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


def held_to(thesis: Thesis | None, closes_at: datetime) -> bool:
    # Only groups that could upload have anything due: their phase started before the deadline closed, they are
    # accepted and, in P1, registered this semester. Everyone else waits for next semester.
    return (
        thesis is not None
        and thesis.phase_started_at < closes_at
        and thesis.status == ThesisStatus.active
        and (thesis.phase != Phase.P1 or thesis.p1_registered)
    )


def _missed(thesis: Thesis | None, s: Standing, now: datetime) -> bool:
    return s.closes_at is not None and now > s.closes_at and s.submitted_at is None and held_to(thesis, s.closes_at)


def standing(db: Session, user: User, now: datetime | None = None) -> Standing:
    template = db.get(MilestoneTemplate, user.phase) if user.phase else None
    return _standing(user, template, group_milestone(db, user), now or _now())


def thesis_standing(db: Session, thesis: Thesis, now: datetime | None = None) -> Standing:
    """The group's own standing: its deadline, submission and freeze. Members' restart requests don't count here."""
    return _thesis_standing(thesis, db.get(MilestoneTemplate, thesis.phase), _milestone(db, thesis), now or _now())


def standings(db: Session, students: list[User]) -> dict[int, Standing]:
    """standing() for many students in three queries, not three per student. For pages that list or count many."""
    templates = {t.phase: t for t in db.scalars(select(MilestoneTemplate))}
    live = [u for u in students if u.thesis_id is not None and u.phase is not None]
    milestones = {
        (g.thesis_id, g.phase): g
        for g in db.scalars(
            select(GroupMilestone).where(
                GroupMilestone.semester_id == current_semester_id(db),
                GroupMilestone.thesis_id.in_({u.thesis_id for u in live}),
            )
        )
    } if live else {}
    now = _now()
    return {
        u.id: _standing(u, templates.get(u.phase), milestones.get((u.thesis_id, u.phase)), now) for u in students
    }


def _standing(user: User, template: MilestoneTemplate | None, gm: GroupMilestone | None, now: datetime) -> Standing:
    # A live thesis only: a completed one has nothing due.
    s = _thesis_standing(user.thesis, template, gm, now) if user.phase else Standing(template, gm)
    if not s.frozen and (user.restart_pending or user.restart_approved):
        # Asking for a fresh start is final: a later deadline extension doesn't reopen this thesis for them.
        s.frozen_reason = "You asked to restart at P1"
    return s


def _thesis_standing(thesis: Thesis, template: MilestoneTemplate | None, gm: GroupMilestone | None, now: datetime) -> Standing:
    s = Standing(template, gm)
    if thesis.frozen_at is not None or _missed(thesis, s, now):
        # Shown as soon as grace ends; saved at the rollover. A deadline extension lifts it before then.
        s.frozen_reason = f"Your group missed the {thesis.phase.value} deadline"
    return s


def _students(db: Session):
    return db.scalars(
        select(User).where(User.role == Role.student, User.approved.is_(True)).with_for_update()
    )


def _withdraw_co_supervisor(thesis: Thesis | None) -> None:
    # A frozen group takes no new co-supervisor, so an invite not yet answered by both is withdrawn.
    if thesis is not None and not thesis.co_supervisor_joined:
        thesis.clear_co_supervisor()


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
    restarted = 0
    for user in _students(db):
        if user.restart_approved:
            _restart(db, user, now)
            restarted += 1
    result = {**advance_phases(db, now), "restarted": restarted}
    db.execute(delete(MilestoneTemplate))
    db.execute(update(Thesis).values(p1_registered=False))  # P1 registration is per semester
    db.add(Semester(started_at=now))  # opens P1 registration for the new semester
    db.commit()
    return result


def advance_phases(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Moves every thesis group on by what it handed in this semester; the semester rollover calls it once the old
    semester's deadlines have all closed, before they are cleared. No commit.

    Submitted P1 -> P2, P2 -> P3. After P3 the thesis is completed, unless the supervisor deferred it: the first
    deferral means P3 again next semester, the second cancels the thesis (its members are free to start again).
    A group that missed its deadline is frozen. A group with nothing due (not registered for P1, or its phase started
    after the deadline) stays where it is. Counts are thesis groups."""
    now = now or _now()
    result = {"advanced": 0, "completed": 0, "deferred": 0, "cancelled": 0, "frozen": 0}
    active = select(Thesis).where(Thesis.status == ThesisStatus.active, Thesis.frozen_at.is_(None))
    for thesis in db.scalars(active.order_by(Thesis.id).with_for_update()).all():
        s = thesis_standing(db, thesis, now)
        if s.frozen:
            thesis.frozen_at = now
            _withdraw_co_supervisor(thesis)
            result["frozen"] += 1
        elif s.submitted_at is None:
            continue  # nothing due this semester: same phase again
        elif thesis.phase in NEXT_PHASE:
            thesis.phase, thesis.phase_started_at = NEXT_PHASE[thesis.phase], now
            result["advanced"] += 1
        elif not thesis.defer_pending:
            thesis.status = ThesisStatus.completed
            result["completed"] += 1
        else:
            thesis.defer_pending, thesis.deferrals = False, thesis.deferrals + 1
            if thesis.deferrals >= MAX_DEFERRALS:
                thesis.status = ThesisStatus.dropped
                for m in thesis.members:
                    m.thesis = None  # cancelled: kept as an archive, and the members can form a new thesis
                result["cancelled"] += 1
            else:
                thesis.phase_started_at = now  # P3 again; last semester's upload no longer counts
                result["deferred"] += 1
    db.flush()
    return result


def register_block(db: Session, user: User) -> str | None:
    """Why this P1 student's accepted group can't register now, or None if it can."""
    thesis = user.thesis
    if user.phase != Phase.P1 or thesis is None or thesis.status not in FORMED:  # active: registered earlier, still in P1
        return "Only a P1 student with an accepted thesis group can register"
    if thesis.p1_registered:
        return "Your group is already registered for P1 this semester"
    if standing(db, user).frozen:
        return "Your account is frozen"
    if registration_upcoming(db):
        return "P1 registration hasn't opened yet"
    if not registration_open(db):
        return "P1 registration is closed, register in the first week of next semester"
    if (needed := MIN_MEMBERS - len(thesis.members)) > 0:
        return f"Your group needs {needed} more {'member' if needed == 1 else 'members'} to register"
    return None


def can_register(db: Session, user: User) -> bool:
    return register_block(db, user) is None


def new_code(db: Session) -> str:
    # "T" + 8 random digits; retry on the rare clash. The unique column guards concurrent registrations.
    while True:
        code = f"T{secrets.randbelow(10**8):08d}"
        if not db.scalar(select(Thesis.id).where(Thesis.code == code)):
            return code


def register_p1(db: Session, user: User) -> None:
    """Student: register their accepted group for P1 this semester. Only in the first week of the semester."""
    user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    if block := register_block(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, block)
    thesis = user.thesis
    thesis.p1_registered, thesis.status = True, ThesisStatus.active
    thesis.code = thesis.code or new_code(db)  # kept if the group registers again in a later semester
    db.commit()


def can_defer(db: Session, thesis: Thesis, s: Standing | None = None) -> bool:
    """s: a member's standing, if the caller already has it (see standings). Members share phase and deadlines."""
    if thesis.status != ThesisStatus.active or thesis.phase != Phase.P3:
        return False
    s = s or thesis_standing(db, thesis)
    return not s.frozen and s.submitted_at is not None


def set_defer(db: Session, supervisor: User, thesis_id: int, defer: bool) -> Thesis:
    """The thesis's supervisor (panel members later): defer, or undo deferring, a thesis whose P3 is submitted.
    Takes effect at the coordinator's semester rollover."""
    thesis = db.scalar(select(Thesis).where(Thesis.id == thesis_id).with_for_update())
    if thesis is None or thesis.supervisor_id != supervisor.id:
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


def release_thesis(db: Session, user: User) -> None:
    """The student stops being a member of their thesis. When the last member goes, a never-registered thesis is deleted
    (no thesis ID, no versions) and an active one is archived with all its versions. No commit."""
    thesis, user.thesis = user.thesis, None
    if thesis is None:
        return
    db.flush()
    if db.scalar(select(func.count()).select_from(User).where(User.thesis_id == thesis.id)):
        return  # other members carry on with it
    if thesis.status in UNREGISTERED:
        db.delete(thesis)
    elif thesis.status == ThesisStatus.active:
        thesis.status, thesis.defer_pending = ThesisStatus.dropped, False


def _restart(db: Session, user: User, now: datetime) -> None:
    """Fresh start at P1 with no thesis and no group, so they can form a new one; the next group gets a new thesis ID."""
    from app.services import group_service  # group_service uses this module, so import at call time

    group_service.drop_membership(db, user)
    release_thesis(db, user)
    user.restart_approved = False


def reject_restart(db: Session, user_id: int) -> User:
    user = _restart_pending(db, user_id)
    user.restart_requested_at = None
    db.commit()
    db.refresh(user)
    return user
