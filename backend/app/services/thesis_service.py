"""Thesis groups: a student asks a supervisor; the group is formed (thesis active, thesis ID issued) when they accept.

A co-supervisor is optional and can only be added to a formed group. They join once both they and the supervisor
accept; either declining just leaves the group without a co-supervisor, and the student can pick someone else.

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
        db.scalars(select(User).where(User.role == Role.faculty, User.approved.is_(True)).order_by(User.full_name))
    )


def can_view(user: User, thesis: Thesis) -> bool:
    # Faculty: the theses they supervise or co-supervise (once joined). A student: their own, archived ones included.
    # The coordinator never sees individual theses.
    if user.role == Role.faculty:
        return thesis.supervisor_id == user.id or (thesis.co_supervisor_id == user.id and thesis.co_supervisor_joined)
    return user.role == Role.student and thesis.student_id == user.id


def mine(db: Session, user: User) -> MyThesisOut:
    s = progress_service.standing(db, user)
    t = user.thesis
    live = t is not None and t.status == ThesisStatus.active and not s.frozen
    return MyThesisOut(
        thesis=user.thesis and ThesisOut.model_validate(user.thesis),
        phase=user.phase,
        frozen_reason=s.frozen_reason,
        restart_pending=user.restart_pending,
        restart_approved=user.restart_approved,
        registration_closes_at=progress_service.registration_closes_at(db),
        registration_open=progress_service.registration_open(db),
        can_register=progress_service.can_register(db, user),
        can_form_group=user.thesis_id is None and user.phase is not None and not s.frozen,
        can_cancel=t is not None and t.status == ThesisStatus.pending,
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
    return member


def request_group(db: Session, user: User, data: ThesisRequestIn) -> MyThesisOut:
    user = _lock_user(db, user)
    if not mine(db, user).can_form_group:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't form a thesis group right now")
    user.thesis = Thesis(student=user, supervisor=_faculty(db, data.supervisor_id, "Supervisor"))
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
    thesis.co_supervisor, thesis.co_supervisor_accepted, thesis.co_supervisor_approved = co, False, False
    db.commit()
    return mine(db, user)


def _clear_co_supervisor(thesis: Thesis) -> None:
    thesis.co_supervisor, thesis.co_supervisor_accepted, thesis.co_supervisor_approved = None, False, False


def cancel_co_supervisor(db: Session, user: User) -> MyThesisOut:
    """Student: withdraw a co-supervisor who hasn't joined yet. One who joined stays."""
    user = _lock_user(db, user)
    thesis = user.thesis
    if thesis is None or thesis.co_supervisor_id is None or thesis.co_supervisor_joined:
        raise HTTPException(status.HTTP_409_CONFLICT, "No co-supervisor request to cancel")
    _clear_co_supervisor(thesis)
    db.commit()
    return mine(db, user)


def cancel(db: Session, user: User) -> MyThesisOut:
    user = _lock_user(db, user)
    thesis = user.thesis
    if thesis is None or thesis.status != ThesisStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending thesis group request to cancel")
    user.thesis = None
    db.delete(thesis)
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


def decide(db: Session, member: User, thesis_id: int, accept: bool) -> None:
    thesis = db.scalar(select(Thesis).where(Thesis.id == thesis_id).with_for_update())
    slot = thesis and _slot(thesis, member)
    if not slot:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending supervision request with that id")
    if slot == "supervisor":
        if accept:
            thesis.status, thesis.code = ThesisStatus.active, new_code(db)
            # A co-supervisor named on an older request was part of what the supervisor just accepted.
            thesis.co_supervisor_approved = thesis.co_supervisor_id is not None
        else:
            # Declined: the student picks again. Never formed, so there are no versions to keep.
            thesis.student.thesis = None
            db.delete(thesis)
    elif not accept:
        _clear_co_supervisor(thesis)  # either one declining: the group stays, without a co-supervisor
    elif slot == "co_supervisor":
        thesis.co_supervisor_accepted = True
    else:
        thesis.co_supervisor_approved = True
    db.commit()


def list_theses(db: Session, user: User) -> list[ThesisDetailOut]:
    """Faculty: theses they supervise or co-supervise, archived ones included. Pending requests are not theses yet."""
    query = (
        select(Thesis)
        .where(Thesis.status != ThesisStatus.pending)
        .order_by(Thesis.id.desc())
        .options(selectinload(Thesis.proposal).selectinload(Proposal.versions))  # one query, not one per thesis
    )
    query = query.where(
        or_(
            Thesis.supervisor_id == user.id,
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


def supervises_live(db: Session, member: User) -> bool:
    """True while the faculty member supervises a pending or active thesis; their account can't be deleted then."""
    return (
        db.scalar(
            select(Thesis.id)
            .where(
                or_(Thesis.supervisor_id == member.id, Thesis.co_supervisor_id == member.id),
                Thesis.status.in_(LIVE),
            )
            .limit(1)
        )
        is not None
    )
