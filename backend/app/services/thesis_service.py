"""Thesis groups: any member of a student group of MIN_MEMBERS or more asks a supervisor (pending), and every member
shares the thesis from then on (users.thesis_id); the group is formed when the supervisor accepts. Any member can
cancel the request or add a co-supervisor. Members who join before P1 registration share it too (group_service). It becomes active, with a
thesis ID, when it registers for P1 (progress_service.register_p1), and only then can it upload.

A co-supervisor is optional and can only be added to a formed group. They join once both they and the supervisor
accept; either declining just leaves the group without a co-supervisor, and the student can pick someone else.

A faculty member who has accepted a group (as supervisor, or as co-supervisor) can't have their account deleted, by
anyone, until each such thesis is completed or dropped (supervises_live). Requests they haven't accepted are dropped
when their deletion runs (drop_requests_to).

Groups can be formed and accepted any time; registering for P1 (progress_service.register_p1) is limited to a week.
Every proposal version is stored under the thesis, so it is never lost when accounts change. The coordinator runs
semesters and accounts and never sees individual theses.
"""

from fastapi import HTTPException, status
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.group import MIN_MEMBERS, Group, GroupMember
from app.models.milestone import Phase
from app.models.proposal import Proposal
from app.models.thesis import FORMED, Thesis, ThesisStatus
from app.models.user import Role, User
from app.schemas.proposal import TitleChangeOut
from app.schemas.thesis import MyThesisOut, PersonOut, SupervisionRequestOut, ThesisDetailOut, ThesisOut, ThesisRequestIn
from app.services import group_service, progress_service


def faculty(db: Session) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .where(User.role == Role.faculty, User.approved.is_(True), User.deletion_approved_at.is_(None))
            .order_by(User.full_name)
        )
    )


def can_view(user: User, thesis: Thesis) -> bool:
    # Faculty: the theses they supervise or co-supervise (once joined). A student: their own, archived ones included.
    # The coordinator never sees individual theses.
    if user.role == Role.faculty:
        return thesis.supervisor_id == user.id or (thesis.co_supervisor_id == user.id and thesis.co_supervisor_joined)
    # shortcut: a member who left (restart, before registration) loses access unless they sent the request; keep a
    # member history table if past members must see archived theses.
    return user.role == Role.student and (user.thesis_id == thesis.id or thesis.student_id == user.id)


def _form_block(db: Session, user: User, frozen: bool) -> str | None:
    """Why this student can't send a supervisor request for their group now, or None if they can."""
    if user.thesis_id is not None or frozen:
        return "Your group already has a thesis" if user.thesis_id is not None else "You can't form a thesis group right now"
    member = group_service.membership(db, user.id)
    if member is None:
        return "Create or join a group first"
    group = member.group
    if (needed := MIN_MEMBERS - len(group.members)) > 0:
        return f"Your group needs {needed} more {'member' if needed == 1 else 'members'} before choosing a supervisor"
    for m in group.members:
        if m.user.thesis_id is not None or progress_service.standing(db, m.user).frozen:
            return f"{m.user.full_name} already has a thesis, so your group can't choose a supervisor yet"
    return None


def mine(db: Session, user: User) -> MyThesisOut:
    s = progress_service.standing(db, user)
    t = user.thesis
    live = t is not None and t.status in FORMED and not s.frozen
    form_block = _form_block(db, user, s.frozen)
    can_form_group = form_block is None
    can_add_co_supervisor = live and t.co_supervisor_id is None
    choices = faculty(db) if can_form_group or can_add_co_supervisor else []
    return MyThesisOut(
        thesis=user.thesis and ThesisOut.model_validate(user.thesis),
        # Shown phase starts at P1 registration; pending/formed groups are still forming (user.phase is P1 for rules).
        phase=user.phase if t is not None and t.status == ThesisStatus.active else None,
        frozen_reason=s.frozen_reason,
        restart_pending=user.restart_pending,
        restart_approved=user.restart_approved,
        registration_opens_at=progress_service.registration_opens_at(db),
        registration_closes_at=progress_service.registration_closes_at(db),
        registration_open=progress_service.registration_open(db),
        registration_upcoming=progress_service.registration_upcoming(db),
        can_register=progress_service.can_register(db, user),
        register_block=progress_service.register_block(db, user) if live and user.phase == Phase.P1 else None,
        can_form_group=can_form_group,
        # Only worth explaining while there is no thesis yet; with one, the page shows the thesis instead.
        form_group_block=form_block if t is None and not s.frozen else None,
        can_cancel=t is not None and t.status == ThesisStatus.pending,
        can_add_co_supervisor=can_add_co_supervisor,
        can_cancel_co_supervisor=t is not None and t.co_supervisor_id is not None and not t.co_supervisor_joined,
        faculty_choices=[PersonOut.model_validate(f) for f in choices if t is None or f.id != t.supervisor_id],
        show_deferral_warning=live and t.status == ThesisStatus.active and t.deferrals > 0,
        show_p1_registration=live and user.phase == Phase.P1,
    )


def _lock_thesis(db: Session, user: User) -> User:
    # Every member acts on the same thesis, so lock its row: two members changing it at once can't both pass the checks.
    if user.thesis_id is not None:
        db.scalar(select(Thesis).where(Thesis.id == user.thesis_id).with_for_update())
    return user


def _faculty(db: Session, user_id: int, what: str) -> User:
    member = db.get(User, user_id)
    if member is None or member.role != Role.faculty or not member.approved:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{what} must be a faculty member")
    if member.deletion_approved_at is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{member.full_name}'s account is being deleted, choose someone else")
    return member


def _lock_group(db: Session, user: User) -> None:
    # Lock the group, then its members, so two members asking at once (or someone joining meanwhile) can't both pass.
    if member := group_service.membership(db, user.id):
        db.scalar(select(Group).where(Group.id == member.group_id).with_for_update())
        db.scalars(select(User).join(GroupMember, GroupMember.user_id == User.id)
                   .where(GroupMember.group_id == member.group_id).order_by(User.id).with_for_update()).all()


def request_group(db: Session, user: User, data: ThesisRequestIn) -> MyThesisOut:
    """Any member of a ready group: ask a supervisor. Every member shares the thesis from now on."""
    _lock_group(db, user)
    db.refresh(user)
    if block := _form_block(db, user, progress_service.standing(db, user).frozen):
        raise HTTPException(status.HTTP_409_CONFLICT, block)
    group = group_service.membership(db, user.id).group
    thesis = Thesis(group=group, student=user, supervisor=_faculty(db, data.supervisor_id, "Supervisor"))
    for m in group.members:
        m.user.thesis = thesis
    db.commit()
    return mine(db, user)


def _release_all(db: Session, thesis: Thesis) -> None:
    """A request that never formed a group goes: every member is free to ask again. No versions exist yet."""
    for m in thesis.members:
        m.thesis = None
    db.flush()
    db.delete(thesis)


def add_co_supervisor(db: Session, user: User, co_supervisor_id: int) -> MyThesisOut:
    """Any member: name a co-supervisor for their formed group. They join once they and the supervisor both accept."""
    user = _lock_thesis(db, user)
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
    """Any member: withdraw a co-supervisor who hasn't joined yet. One who joined stays."""
    user = _lock_thesis(db, user)
    thesis = user.thesis
    if thesis is None or thesis.co_supervisor_id is None or thesis.co_supervisor_joined:
        raise HTTPException(status.HTTP_409_CONFLICT, "No co-supervisor request to cancel")
    thesis.clear_co_supervisor()
    db.commit()
    return mine(db, user)


def cancel(db: Session, user: User) -> MyThesisOut:
    """Any member: take back the group's supervisor request while it waits."""
    user = _lock_thesis(db, user)
    thesis = user.thesis
    if thesis is None or thesis.status != ThesisStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "No pending thesis group request to cancel")
    _release_all(db, thesis)
    db.commit()
    db.refresh(user)
    return mine(db, user)


def _requests(member: User) -> Select:
    active = Thesis.status.in_(FORMED)
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
    if thesis.status in FORMED and thesis.co_supervisor_id is not None:
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
    if accept and member.deletion_approved_at is not None:
        # Accepting would tie the account to this group, so the approved deletion could never run.
        raise HTTPException(status.HTTP_409_CONFLICT, "Your account is being deleted, so you can't accept groups. Ask the coordinator to cancel it first")
    if slot != "supervisor" and accept and any(progress_service.standing(db, m).frozen for m in thesis.members):
        raise HTTPException(status.HTTP_409_CONFLICT, "The group is frozen, so no co-supervisor can join now")
    if slot == "supervisor":
        if accept:
            thesis.status = ThesisStatus.formed  # active, with a thesis ID, once it registers for P1
            # A co-supervisor named on an older request was part of what the supervisor just accepted.
            thesis.co_supervisor_approved = thesis.co_supervisor_id is not None
        else:
            _release_all(db, thesis)  # declined: the group picks again
    elif not accept:
        thesis.clear_co_supervisor()  # either one declining: the group stays, without a co-supervisor
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
        # One query each, not one per thesis.
        .options(
            selectinload(Thesis.proposal).selectinload(Proposal.versions),
            selectinload(Thesis.members),
            selectinload(Thesis.supervisor),
            selectinload(Thesis.co_supervisor),
            selectinload(Thesis.title_changes),
        )
    )
    query = query.where(
        or_(
            Thesis.supervisor_id == user.id,
            (Thesis.co_supervisor_id == user.id) & Thesis.co_supervisor_accepted.is_(True) & Thesis.co_supervisor_approved.is_(True),
        )
    )
    theses = list(db.scalars(query))
    standings = progress_service.standings(db, [m for t in theses for m in t.members])
    out = []
    for t in theses:
        row = ThesisDetailOut.model_validate(t)
        row.is_supervisor = t.supervisor_id == user.id
        pending = [c for c in t.title_changes if c.status == "pending"]
        row.title_change_request = pending and TitleChangeOut.model_validate(pending[0]) or None
        # Deferral is the supervisor's call for now (panel members later).
        row.can_defer = row.is_supervisor and (t.defer_pending or progress_service.can_defer(db, t, t.members and standings.get(t.members[0].id)))
        out.append(row)
    return out


def supervises_live(db: Session, member: User) -> bool:
    """True while the faculty member has accepted a group whose thesis is not completed or dropped yet: as supervisor
    (a formed or active thesis), or as co-supervisor (accepted, even before the supervisor agrees). Their account can't be
    deleted then. A frozen student's thesis is still active: it counts until it is dropped at a restart."""
    active = Thesis.status.in_(FORMED)
    return (
        db.scalar(
            select(Thesis.id)
            .where(
                or_(
                    (Thesis.supervisor_id == member.id) & active,
                    (Thesis.co_supervisor_id == member.id) & Thesis.co_supervisor_accepted.is_(True) & active,
                )
            )
            .limit(1)
        )
        is not None
    )


def drop_requests_to(db: Session, member: User) -> None:
    """Their account is being deleted: drop requests they never accepted. Group requests go, like a decline (never
    formed, so no versions); co-supervisor invites are withdrawn, leaving the group as it was."""
    for t in db.scalars(select(Thesis).where(Thesis.co_supervisor_id == member.id)):
        t.clear_co_supervisor()
    for t in db.scalars(select(Thesis).where(Thesis.supervisor_id == member.id, Thesis.status == ThesisStatus.pending)).all():
        _release_all(db, t)
