"""Thesis groups: a student asks a supervisor; the group is formed (thesis active, thesis ID issued) when they accept.

A co-supervisor is optional and can only be added to a formed group. They join once both they and the supervisor
accept; either declining just leaves the group without a co-supervisor, and the student can pick someone else.

A faculty member whose account deletion is approved is shown to the rest of each group (leaving) and can't be picked.
When it runs (remove_faculty) they leave every group: a formed group they supervised goes back to pending, keeping its
thesis ID and versions, and the student picks a new supervisor the same way as the first.

Groups can be formed and accepted any time; registering for P1 (progress_service.register_p1) is limited to a week.
Every proposal version is stored under the thesis, so it is never lost when accounts change. The coordinator runs
semesters and accounts and never sees individual theses.
"""

import secrets

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.milestone import Phase
from app.models.proposal import Proposal
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User
from app.schemas.user import LeavingOut
from app.schemas.thesis import MyThesisOut, SupervisionRequestOut, ThesisDetailOut, ThesisOut, ThesisRequestIn
from app.services import progress_service, proposal_service  # proposal_service imports us too; used at call time only

LIVE = (ThesisStatus.pending, ThesisStatus.active)


def new_code(db: Session) -> str:
    # "T" + 8 random digits; retry on the rare clash. The unique column guards concurrent accepts.
    while True:
        code = f"T{secrets.randbelow(10**8):08d}"
        if not db.scalar(select(Thesis.id).where(Thesis.code == code)):
            return code


def faculty(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == Role.faculty, User.approved.is_(True), User.deletion_approved_at.is_(None))
            .order_by(User.full_name)
        )
    )


def can_view(user: User, thesis: Thesis) -> bool:
    # Faculty: the theses they supervise (once accepted) or co-supervise (once joined). A student: their own, archived
    # ones included. The coordinator never sees individual theses.
    if user.role == Role.faculty:
        return thesis.supervisor_id == user.id and thesis.status != ThesisStatus.pending or (thesis.co_supervisor_id == user.id and thesis.co_supervisor_joined)
    return user.role == Role.student and thesis.student_id == user.id


def mine(db: Session, user: User) -> MyThesisOut:
    s = progress_service.standing(db, user)
    t = user.thesis
    live = t is not None and t.status == ThesisStatus.active and not s.frozen
    needs_supervisor = t is not None and t.status == ThesisStatus.pending and t.supervisor_id is None
    return MyThesisOut(
        thesis=user.thesis and ThesisOut.model_validate(user.thesis),
        phase=user.phase,
        frozen_reason=s.frozen_reason,
        restart_pending=user.restart_pending,
        restart_approved=user.restart_approved,
        registration_closes_at=progress_service.registration_closes_at(db),
        registration_open=progress_service.registration_open(db),
        can_register=progress_service.can_register(db, user),
        can_form_group=(user.thesis_id is None or needs_supervisor) and user.phase is not None and not s.frozen,
        can_cancel=t is not None and t.status == ThesisStatus.pending and t.supervisor_id is not None,
        can_add_co_supervisor=live and t.co_supervisor_id is None,
        can_cancel_co_supervisor=t is not None and t.co_supervisor_id is not None and not t.co_supervisor_joined,
        show_deferral_warning=live and t.deferrals > 0,
        show_p1_registration=live and user.phase == Phase.P1,
    )


def _lock_user(db: Session, user: User) -> User:
    # Row lock so two group requests from one student can't both pass the checks.
    return db.scalar(select(User).where(User.id == user.id).with_for_update())


def _faculty(db: Session, user_id: int, what: str) -> User:
    member = db.get(User, user_id)
    if member is None or member.role != Role.faculty or not member.approved:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{what} must be a faculty member")
    if member.deletion_approved_at is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{member.full_name}'s account is being deleted, choose someone else")
    return member


def request_group(db: Session, user: User, data: ThesisRequestIn) -> MyThesisOut:
    user = _lock_user(db, user)
    if not mine(db, user).can_form_group:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't form a thesis group right now")
    supervisor = _faculty(db, data.supervisor_id, "Supervisor")
    if user.thesis is None:
        user.thesis = Thesis(student=user, supervisor=supervisor)
    elif supervisor.id == user.thesis.co_supervisor_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Supervisor must be someone else than your co-supervisor")
    else:
        user.thesis.supervisor = supervisor  # a formed group whose supervisor left: same thesis ID and versions
    db.commit()
    return mine(db, user)


def add_co_supervisor(db: Session, user: User, co_supervisor_id: int) -> MyThesisOut:
    """Student: name a co-supervisor for their formed group. They join once they and the supervisor both accept."""
    user = _lock_user(db, user)
    if not mine(db, user).can_add_co_supervisor:
        raise HTTPException(status.HTTP_409_CONFLICT, "A co-supervisor can only be added to a formed group that has none")
    co = _faculty(db, co_supervisor_id, "Co-supervisor")
    thesis = user.thesis
    if co.id == thesis.supervisor_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Co-supervisor must be a different faculty member")
    thesis.clear_co_supervisor()
    thesis.co_supervisor = co
    db.commit()
    return mine(db, user)


def cancel_co_supervisor(db: Session, user: User) -> MyThesisOut:
    """Student: withdraw a co-supervisor who hasn't joined yet. One who joined stays."""
    user = _lock_user(db, user)
    thesis = user.thesis
    if thesis is None or thesis.co_supervisor_id is None or thesis.co_supervisor_joined:
        raise HTTPException(status.HTTP_409_CONFLICT, "No co-supervisor request to cancel")
    thesis.clear_co_supervisor()
    db.commit()
    return mine(db, user)


def cancel(db: Session, user: User) -> MyThesisOut:
    user = _lock_user(db, user)
    thesis = user.thesis
    if thesis is None or thesis.status != ThesisStatus.pending or thesis.supervisor_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending thesis group request to cancel")
    if thesis.never_formed:
        user.thesis = None
        db.delete(thesis)
    else:
        thesis.supervisor = None  # a formed group keeps its ID and versions; the student picks again
    db.commit()
    return mine(db, user)


def _requests(member: User) -> Select:
    active = Thesis.status == ThesisStatus.active
    return select(Thesis).where(
        or_(
            (Thesis.supervisor_id == member.id) & (Thesis.status == ThesisStatus.pending),
            (Thesis.co_supervisor_id == member.id) & Thesis.co_supervisor_accepted.is_(False) & active,
            (Thesis.supervisor_id == member.id) & Thesis.co_supervisor_id.is_not(None)
            & Thesis.co_supervisor_approved.is_(False) & active,
        )
    )


def _slot(thesis: Thesis, member: User) -> str | None:
    """What this faculty member is asked to decide on this thesis, if anything."""
    if thesis.status == ThesisStatus.pending and thesis.supervisor_id == member.id:
        return "supervisor"
    if thesis.status == ThesisStatus.active and thesis.co_supervisor_id is not None:
        if thesis.co_supervisor_id == member.id and not thesis.co_supervisor_accepted:
            return "co_supervisor"
        if thesis.supervisor_id == member.id and not thesis.co_supervisor_approved:
            return "co_supervisor_approval"
    return None


def requests_for(db: Session, member: User) -> list[SupervisionRequestOut]:
    rows = db.scalars(_requests(member).order_by(Thesis.created_at))
    return [SupervisionRequestOut(**ThesisOut.model_validate(t).model_dump(), slot=_slot(t, member)) for t in rows]


def count_requests(db: Session, member: User) -> int:
    # Polled every 10s by the UI badge, so count in SQL.
    return db.scalar(_requests(member).with_only_columns(func.count()))


def decide(db: Session, member: User, thesis_id: int, accept: bool, co_supervisor_id: int | None = None) -> None:
    """co_supervisor_id: who the deciding page showed. The student may have swapped co-supervisors since then."""
    thesis = db.scalar(select(Thesis).where(Thesis.id == thesis_id).with_for_update())
    slot = thesis and _slot(thesis, member)
    if not slot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending supervision request with that id")
    if slot != "supervisor" and co_supervisor_id is not None and co_supervisor_id != thesis.co_supervisor_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "The student changed the co-supervisor, so reload and decide again")
    if slot != "supervisor" and accept and thesis.student and progress_service.standing(db, thesis.student).frozen:
        raise HTTPException(status.HTTP_409_CONFLICT, "The student's account is frozen, so no co-supervisor can join now")
    if slot == "supervisor":
        if accept:
            # A formed group taking a new supervisor keeps its thesis ID.
            thesis.status, thesis.code = ThesisStatus.active, thesis.code or new_code(db)
            # A co-supervisor already named (an older request, or the group's before its supervisor left) was part of
            # what the supervisor just accepted.
            thesis.co_supervisor_approved = thesis.co_supervisor_id is not None
        elif thesis.never_formed:
            # Declined: the student picks again. Never formed, so there are no versions to keep.
            thesis.student.thesis = None
            db.delete(thesis)
        else:
            thesis.supervisor = None  # a formed group keeps its ID and versions; the student picks again
    elif not accept:
        thesis.clear_co_supervisor()  # either one declining: the group stays, without a co-supervisor
    elif slot == "co_supervisor":
        thesis.co_supervisor_accepted = True
    else:
        thesis.co_supervisor_approved = True
    db.commit()


def list_theses(db: Session, user: User) -> list[ThesisDetailOut]:
    """Faculty: theses they supervise or co-supervise, archived ones included. Pending requests are not theses yet,
    but a joined co-supervisor keeps seeing a group while it picks a new supervisor."""
    query = (
        select(Thesis)
        .order_by(Thesis.id.desc())
        .options(selectinload(Thesis.proposal).selectinload(Proposal.versions))  # one query, not one per thesis
    )
    query = query.where(
        or_(
            (Thesis.supervisor_id == user.id) & (Thesis.status != ThesisStatus.pending),
            (Thesis.co_supervisor_id == user.id) & Thesis.co_supervisor_accepted.is_(True) & Thesis.co_supervisor_approved.is_(True),
        )
    )
    out = []
    for t in db.scalars(query):
        row = ThesisDetailOut.model_validate(t)
        proposal_service.staff_view(db, user, t, row.versions)
        row.is_supervisor = t.supervisor_id == user.id
        # Deferral is the supervisor's call for now (panel members later).
        row.can_defer = row.is_supervisor and (t.defer_pending or progress_service.can_defer(db, t))
        out.append(row)
    return out


def leaving(db: Session, user: User) -> list[LeavingOut]:
    """Members of this user's live groups whose account deletion is approved, so the rest of the group is told in time."""
    member = or_(Thesis.student_id == user.id, Thesis.supervisor_id == user.id, Thesis.co_supervisor_id == user.id)
    out = []
    for t in db.scalars(select(Thesis).where(member, Thesis.status.in_(LIVE)).order_by(Thesis.id)):
        for role, person in (("student", t.student), ("supervisor", t.supervisor), ("co_supervisor", t.co_supervisor)):
            if person is not None and person.id != user.id and person.deletion_executes_at is not None:
                out.append(
                    LeavingOut(full_name=person.full_name, member=role, thesis_code=t.code, executes_at=person.deletion_executes_at)
                )
    return out


def remove_faculty(db: Session, member: User) -> None:
    """Their account is being deleted: take them off every group. A group they supervised goes back to picking a
    supervisor, keeping its thesis ID and versions; a request they never accepted is dropped, like a decline."""
    for t in db.scalars(select(Thesis).where(Thesis.co_supervisor_id == member.id)):
        t.clear_co_supervisor()
    for t in db.scalars(select(Thesis).where(Thesis.supervisor_id == member.id, Thesis.status.in_(LIVE))):
        if t.never_formed:
            if t.student:
                t.student.thesis = None
            db.delete(t)
        else:
            t.supervisor, t.status = None, ThesisStatus.pending
