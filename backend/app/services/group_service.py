"""Student groups (F6): a student creates a group of 3 to 5, invites others, and invitations are accepted or declined.

Rules: a student is in one group; only the leader invites; invitations lapse after INVITE_WINDOW; live invitations
count toward the size limit, so an accepted invitation always has room. Joining or creating a group cancels the
student's other invitations. The teammate finder lists students without a group, searchable by interests and skills.
"""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.group import (
    INVITE_WINDOW,
    MAX_MEMBERS,
    MIN_MEMBERS,
    Group,
    GroupMember,
    Invitation,
    InvitationStatus,
    StudentProfile,
)
from app.models.user import Role, User
from app.schemas.group import (
    GroupCreate,
    GroupOut,
    InvitationOut,
    MyGroupOut,
    ProfileIn,
    ProfileOut,
    TeammateOut,
)
from app.schemas.thesis import PersonOut

MAX_RESULTS = 50


def _live():
    # Not answered yet and younger than INVITE_WINDOW.
    return (Invitation.status == InvitationStatus.pending) & (
        Invitation.created_at > datetime.now(timezone.utc) - INVITE_WINDOW
    )


def _lock_user(db: Session, user: User) -> User:
    # Row lock so two requests from one student can't both pass the same check.
    return db.scalar(select(User).where(User.id == user.id).with_for_update())


def membership(db: Session, user_id: int) -> GroupMember | None:
    return db.scalar(select(GroupMember).where(GroupMember.user_id == user_id))


def _lock_group(db: Session, group_id: int) -> Group:
    return db.scalar(select(Group).where(Group.id == group_id).with_for_update())


def _live_invitations(db: Session, **where) -> list[Invitation]:
    return list(db.scalars(select(Invitation).where(_live(), *[getattr(Invitation, k) == v for k, v in where.items()])
                           .order_by(Invitation.created_at)))


def _tags(text: str) -> list[str]:
    return [t for t in text.split(",") if t]


def _person(user: User | None) -> PersonOut | None:
    return user and PersonOut.model_validate(user)


def _invitation_out(i: Invitation) -> InvitationOut:
    return InvitationOut(
        id=i.id,
        group_id=i.group_id,
        group_name=i.group.name,
        member_count=len(i.group.members),
        invitee=_person(i.invitee),
        invited_by=_person(i.invited_by),
        created_at=i.created_at,
        expires_at=i.expires_at,
    )


def _group_out(group: Group) -> GroupOut:
    return GroupOut(
        id=group.id,
        name=group.name,
        leader=_person(group.leader),
        members=[_person(m.user) for m in group.members],
        is_ready=group.is_ready,
        members_needed=max(0, MIN_MEMBERS - len(group.members)),
        created_at=group.created_at,
    )


def mine(db: Session, user: User) -> MyGroupOut:
    member = membership(db, user.id)
    group = member.group if member else None
    is_leader = group is not None and group.leader_id == user.id
    sent = _live_invitations(db, group_id=group.id) if group else []
    slots = MAX_MEMBERS - len(group.members) - len(sent) if group else 0
    return MyGroupOut(
        group=group and _group_out(group),
        is_leader=is_leader,
        can_create=group is None,
        can_invite=is_leader and slots > 0,
        can_leave=group is not None,
        open_slots=max(0, slots),
        sent_invitations=[_invitation_out(i) for i in sent],
        received_invitations=[] if group else [_invitation_out(i) for i in _live_invitations(db, invitee_id=user.id)],
    )


def count_invitations(db: Session, user: User) -> int:
    # Polled every 10s by the UI badge, so count in SQL.
    return db.scalar(select(func.count()).select_from(Invitation).where(_live(), Invitation.invitee_id == user.id))


def _cancel_invitations_to(db: Session, user_id: int, keep_id: int | None = None) -> None:
    query = update(Invitation).where(_live(), Invitation.invitee_id == user_id)
    if keep_id is not None:
        query = query.where(Invitation.id != keep_id)
    db.execute(query.values(status=InvitationStatus.cancelled), execution_options={"synchronize_session": "fetch"})


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        # A parallel request put the same student in a group after the checks above.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Another change happened at the same time, try again") from None


def create(db: Session, user: User, data: GroupCreate) -> MyGroupOut:
    user = _lock_user(db, user)
    if membership(db, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already in a group")
    group = Group(name=data.name, leader=user)
    group.members.append(GroupMember(user=user))
    db.add(group)
    _cancel_invitations_to(db, user.id)  # they chose to lead their own group
    _commit(db)
    return mine(db, user)


def invite(db: Session, user: User, student_id: int) -> MyGroupOut:
    member = membership(db, user.id)
    if member is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Create a group first, then invite students")
    group = _lock_group(db, member.group_id)
    if group.leader_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the group leader can invite students")
    invitee = db.get(User, student_id)
    if invitee is None or invitee.role != Role.student or not invitee.approved or invitee.id == user.id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Choose another student to invite")
    if membership(db, invitee.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "That student is already in a group")
    profile = db.get(StudentProfile, invitee.id)
    if profile and not profile.open_to_invites:
        raise HTTPException(status.HTTP_409_CONFLICT, "That student is not taking invitations")
    if _live_invitations(db, group_id=group.id, invitee_id=invitee.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already invited that student")
    if len(group.members) + len(_live_invitations(db, group_id=group.id)) >= MAX_MEMBERS:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Your group is full: {MAX_MEMBERS} members, counting invitations still waiting"
        )
    db.add(Invitation(group_id=group.id, invitee_id=invitee.id, invited_by_id=user.id))
    _commit(db)
    return mine(db, user)


def cancel_invitation(db: Session, user: User, invitation_id: int) -> MyGroupOut:
    member = membership(db, user.id)
    invitation = db.get(Invitation, invitation_id)
    if member is None or invitation is None or invitation.group_id != member.group_id or not invitation.is_live:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending invitation with that id")
    if invitation.group.leader_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the group leader can cancel invitations")
    invitation.status = InvitationStatus.cancelled
    db.commit()
    return mine(db, user)


def decide(db: Session, user: User, invitation_id: int, accept: bool) -> MyGroupOut:
    user = _lock_user(db, user)
    invitation = db.get(Invitation, invitation_id)
    if invitation is None or invitation.invitee_id != user.id or not invitation.is_live:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending invitation with that id")
    if not accept:
        invitation.status = InvitationStatus.declined
        db.commit()
        return mine(db, user)
    group = _lock_group(db, invitation.group_id)
    if membership(db, user.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already in a group")
    if len(group.members) >= MAX_MEMBERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "That group is already full")
    group.members.append(GroupMember(user=user))
    invitation.status = InvitationStatus.accepted
    _cancel_invitations_to(db, user.id, keep_id=invitation.id)
    _commit(db)
    return mine(db, user)


def _remove(db: Session, user: User, member: GroupMember) -> None:
    group = _lock_group(db, member.group_id)
    others = [m for m in group.members if m.user_id != user.id]
    if not others:
        db.delete(group)  # last one out: the group and its invitations go
    else:
        db.delete(member)
        if group.leader_id == user.id:
            group.leader_id = others[0].user_id  # the longest-standing member leads
    db.flush()


def leave(db: Session, user: User) -> MyGroupOut:
    user = _lock_user(db, user)
    member = membership(db, user.id)
    if member is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are not in a group")
    _remove(db, user, member)
    db.commit()
    return mine(db, user)


def drop_membership(db: Session, user: User) -> None:
    """Called before an account is deleted (account_service): leave the group so it keeps a leader. No commit."""
    if member := membership(db, user.id):
        _remove(db, user, member)


def teammates(db: Session, user: User, q: str = "") -> list[TeammateOut]:
    """Students without a group who accept invitations, optionally matching q in their interests or skills."""
    member = membership(db, user.id)
    in_group = select(GroupMember.id).where(GroupMember.user_id == User.id).exists()
    query = (
        select(User, StudentProfile)
        .outerjoin(StudentProfile, StudentProfile.user_id == User.id)
        .where(
            User.role == Role.student,
            User.approved.is_(True),
            User.id != user.id,
            ~in_group,
            or_(StudentProfile.user_id.is_(None), StudentProfile.open_to_invites.is_(True)),
        )
    )
    if q := q.strip():
        query = query.where(
            or_(StudentProfile.interests.icontains(q, autoescape=True), StudentProfile.skills.icontains(q, autoescape=True))
        )
    rows = db.execute(query.order_by(User.full_name).limit(MAX_RESULTS)).all()
    state = mine(db, user) if member else None
    invited = {i.invitee.id for i in state.sent_invitations} if state else set()
    return [
        TeammateOut(
            **PersonOut.model_validate(u).model_dump(),
            interests=_tags(p.interests) if p else [],
            skills=_tags(p.skills) if p else [],
            bio=p.bio if p else "",
            invited=u.id in invited,
            can_invite=bool(state and state.can_invite and u.id not in invited),
        )
        for u, p in rows
    ]


def _profile_out(p: StudentProfile | None) -> ProfileOut:
    if p is None:
        return ProfileOut()
    return ProfileOut(interests=_tags(p.interests), skills=_tags(p.skills), bio=p.bio, open_to_invites=p.open_to_invites)


def get_profile(db: Session, user: User) -> ProfileOut:
    return _profile_out(db.get(StudentProfile, user.id))


def save_profile(db: Session, user: User, data: ProfileIn) -> ProfileOut:
    db.merge(
        StudentProfile(
            user_id=user.id,
            interests=",".join(data.interests),
            skills=",".join(data.skills),
            bio=data.bio.strip(),
            open_to_invites=data.open_to_invites,
        )
    )
    db.commit()
    return get_profile(db, user)
