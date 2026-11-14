"""Thesis groups: a student picks a supervisor (required) and a co-supervisor (optional); each must accept.

Groups can be formed and accepted any time; registering for P1 (progress_service.register_p1) is limited to a week.

The supervisor accepting makes the thesis active and issues its thesis ID. Every proposal version is
stored under that thesis, so it is never lost when accounts change.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.milestone import Phase
from app.models.proposal import Proposal
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User
from app.schemas.thesis import MyThesisOut, SupervisionRequestOut, ThesisDetailOut, ThesisOut, ThesisRequestIn
from app.services import progress_service

LIVE = (ThesisStatus.pending, ThesisStatus.active)


def faculty(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == Role.faculty, User.approved.is_(True)).order_by(User.full_name))
    )


def can_view(user: User, thesis: Thesis) -> bool:
    # Coordinator sees all; faculty the theses they supervise; a student their own, archived ones included.
    if user.role == Role.coordinator:
        return True
    if user.role == Role.faculty:
        return thesis.supervisor_id == user.id or (thesis.co_supervisor_id == user.id and thesis.co_supervisor_accepted)
    return thesis.student_id == user.id


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
        show_deferral_warning=live and t.deferrals > 0,
        show_p1_registration=live and user.phase == Phase.P1,
    )


def _lock_user(db: Session, user: User) -> User:
    # Row lock so two group requests from one student can't both pass the checks.
    return db.scalar(select(User).where(User.id == user.id).with_for_update())


def _faculty(db: Session, user_id: int, what: str) -> User:
    member = db.get(User, user_id)
    if member is None or member.role != Role.faculty or not member.approved:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{what} must be a faculty member")
    return member


def request_group(db: Session, user: User, data: ThesisRequestIn) -> MyThesisOut:
    user = _lock_user(db, user)
    if not mine(db, user).can_form_group:
        raise HTTPException(status.HTTP_409_CONFLICT, "You can't form a thesis group right now")
    supervisor = _faculty(db, data.supervisor_id, "Supervisor")
    co = data.co_supervisor_id and _faculty(db, data.co_supervisor_id, "Co-supervisor")
    if co and co.id == supervisor.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Co-supervisor must be a different faculty member")
    user.thesis = Thesis(student=user, supervisor=supervisor, co_supervisor=co or None)
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
    return select(Thesis).where(
        or_(
            (Thesis.supervisor_id == member.id) & (Thesis.status == ThesisStatus.pending),
            (Thesis.co_supervisor_id == member.id) & Thesis.co_supervisor_accepted.is_(False) & Thesis.status.in_(LIVE),
        )
    )


def requests_for(db: Session, member: User) -> list[SupervisionRequestOut]:
    rows = db.scalars(_requests(member).order_by(Thesis.created_at))
    return [
        SupervisionRequestOut(
            **ThesisOut.model_validate(t).model_dump(),
            slot="supervisor" if t.supervisor_id == member.id else "co_supervisor",
        )
        for t in rows
    ]


def count_requests(db: Session, member: User) -> int:
    # Polled every 10s by the UI badge, so count in SQL.
    return db.scalar(_requests(member).with_only_columns(func.count()))


def decide(db: Session, member: User, thesis_id: int, accept: bool) -> None:
    thesis = db.scalar(select(Thesis).where(Thesis.id == thesis_id).with_for_update())
    if thesis and thesis.supervisor_id == member.id and thesis.status == ThesisStatus.pending:
        if accept:
            thesis.status = ThesisStatus.active
        else:
            # Declined: the student picks again. Never accepted, so there are no versions to keep.
            thesis.student.thesis = None
            db.delete(thesis)
    elif thesis and thesis.co_supervisor_id == member.id and not thesis.co_supervisor_accepted and thesis.status in LIVE:
        if accept:
            thesis.co_supervisor_accepted = True
        else:
            thesis.co_supervisor = None  # the co-supervisor is optional
    else:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending supervision request with that id")
    db.commit()


def list_theses(db: Session, user: User) -> list[ThesisDetailOut]:
    """Faculty: theses they supervise. Coordinator: every thesis, archived ones included. Pending requests are not theses yet."""
    query = (
        select(Thesis)
        .where(Thesis.status != ThesisStatus.pending)
        .order_by(Thesis.id.desc())
        .options(selectinload(Thesis.proposal).selectinload(Proposal.versions))  # one query, not one per thesis
    )
    if user.role == Role.faculty:
        query = query.where(
            or_(
                Thesis.supervisor_id == user.id,
                (Thesis.co_supervisor_id == user.id) & Thesis.co_supervisor_accepted.is_(True),
            )
        )
    out = []
    for t in db.scalars(query):
        row = ThesisDetailOut.model_validate(t)
        for v in row.versions:
            v.can_delete = False  # only the student removes versions, from their proposal page
        row.can_defer = user.role == Role.coordinator and (t.defer_pending or progress_service.can_defer(db, t))
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
