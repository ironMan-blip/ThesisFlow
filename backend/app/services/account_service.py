"""Requests the coordinator decides (sign-ups), scheduled account deletions, and the coordinator's account list.

Deleting an account: the user asks with a reason and the coordinator approves or rejects. Approval starts a
DELETION_DELAY wait (the account stays usable, only the coordinator can cancel), then run_due_deletions deletes it.
The coordinator's own deletes count as approved at once.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.thesis import UNREGISTERED, ThesisStatus
from app.models.user import DELETION_DELAY, REVIEW_WINDOW, Role, User
from app.services import group_service, progress_service, proposal_service, thesis_service

log = logging.getLogger(__name__)


def _registrations() -> Select:
    # A request older than the review window has expired (login says so, register replaces it): not approvable.
    return select(User).where(User.approved.is_(False), User.created_at > datetime.now(timezone.utc) - REVIEW_WINDOW)


def _deletions() -> Select:
    return select(User).where(User.deletion_requested_at.is_not(None))


def pending_registrations(db: Session) -> list[User]:
    return list(db.scalars(_registrations().order_by(User.created_at)))


def _pending(db: Session, user_id: int) -> User:
    user = db.scalar(_registrations().where(User.id == user_id))
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending registration request with that id")
    return user


def approve_registration(db: Session, user_id: int) -> User:
    user = _pending(db, user_id)
    # A student's phase starts when they can log in, so a sign-up approved late isn't counted as missing a deadline.
    user.approved, user.phase_started_at = True, datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def reject_registration(db: Session, user_id: int) -> None:
    # Deleting frees the email so the person can register again. Not an account yet, so no waiting period.
    db.delete(_pending(db, user_id))
    db.commit()


def _schedule(db: Session, user: User, by: User, reason: str, approved: bool) -> User:
    _check_deletable(db, user)
    if user.deletion_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account's deletion is already requested")
    now = datetime.now(timezone.utc)
    user.deletion_requested_at, user.deletion_reason, user.deletion_requested_by_id = now, reason, by.id
    user.deletion_approved_at = now if approved else None
    db.commit()
    db.refresh(user)
    return user


def request_deletion(db: Session, user: User, reason: str) -> User:
    # Waits for the coordinator. The user can't take the request back; only the coordinator can reject or cancel it.
    locked = _locked(db, user.id)
    if locked is None:  # deleted after the token was checked
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This account no longer exists")
    return _schedule(db, locked, user, reason, approved=False)


def schedule_deletion(db: Session, coordinator: User, user_id: int, reason: str) -> User:
    """Coordinator: delete an account. Counts as approved, so the wait starts now and it can still be cancelled."""
    user = _locked(db, user_id)
    if user is None or not user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that id")
    return _schedule(db, user, coordinator, reason, approved=True)


def approve_deletion(db: Session, user_id: int) -> User:
    """Coordinator: approve a user's request. The account is deleted DELETION_DELAY from now unless cancelled."""
    user = _locked(db, user_id)
    if user is None or not user.deletion_pending or user.deletion_approved_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No deletion request waiting for approval with that id")
    _check_deletable(db, user)
    user.deletion_approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def pending_deletions(db: Session) -> list[User]:
    return list(db.scalars(_deletions().order_by(User.deletion_requested_at)))


def _locked(db: Session, user_id: int) -> User | None:
    # Row lock: a cancel and the deletion job must not both act on one account.
    return db.scalar(select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True))


def _check_deletable(db: Session, user: User) -> None:
    if user.role == Role.coordinator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The coordinator account cannot be deleted")
    if user.role == Role.faculty and thesis_service.supervises_live(db, user):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This faculty member supervises or co-supervises a thesis that isn't completed or dropped yet, so the account is kept",
        )


def pending_counts(db: Session, user: User) -> dict[str, int]:
    # Badge counts keyed by tool: the coordinator decides account requests, faculty answer supervision and delete requests.
    if user.role == Role.faculty:
        # Supervision requests plus students' version delete requests waiting for this supervisor.
        return {"theses": thesis_service.count_requests(db, user) + proposal_service.count_delete_requests(db, user)}
    if user.role == Role.student:
        counts = {"proposal": proposal_service.count_staff_deletes(db, user), "thesis": group_service.count_invitations(db, user)}
        return {tool: n for tool, n in counts.items() if n}
    # Polled every 10s by the UI, so count in SQL instead of loading the rows.
    count = lambda q: db.scalar(q.with_only_columns(func.count()))
    return {
        "registration_requests": count(_registrations()),
        "deletion_requests": count(_deletions().where(User.deletion_approved_at.is_(None))),  # awaiting a decision
        "restart_requests": progress_service.count_restarts(db),
    }


def list_accounts(db: Session, role: Role | None = None, id_prefix: str = "") -> list[User]:
    # Unapproved sign-ups are not accounts yet; they live in pending_registrations.
    # The coordinator is the admin login, not a member account.
    query = select(User).where(
        User.approved.is_(True), User.role != Role.coordinator, User.id_number.startswith(id_prefix, autoescape=True)
    )
    if role:
        query = query.where(User.role == role)
    return list(db.scalars(query.order_by(User.role, User.full_name)))


def _delete(db: Session, user: User) -> None:
    # The thesis and every proposal version stay as an archive; the foreign keys only clear the user.
    group_service.drop_membership(db, user)  # hands leadership on before the user row goes
    thesis, user.thesis = user.thesis, None
    if thesis is not None and thesis.status in UNREGISTERED:
        db.delete(thesis)  # never registered, so no thesis ID and no versions
    elif thesis is not None and thesis.status == ThesisStatus.active:
        thesis.status = ThesisStatus.dropped
    if user.role == Role.faculty:
        thesis_service.drop_requests_to(db, user)  # supervises_live already ruled out any group they accepted
    db.delete(user)


def cancel_deletion(db: Session, user_id: int) -> User:
    """Coordinator only: rejects a request, or cancels an approved one any time before it runs."""
    user = _locked(db, user_id)
    if user is None or not user.deletion_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No deletion request with that id")
    user.deletion_requested_at = user.deletion_approved_at = user.deletion_reason = user.deletion_requested_by_id = None
    db.commit()
    db.refresh(user)
    return user


def run_due_deletions(db: Session, now: datetime | None = None) -> int:
    """Delete every account whose wait is over. Run by the background job in app.main. Returns how many went."""
    cutoff = (now or datetime.now(timezone.utc)) - DELETION_DELAY
    deleted = 0
    for user_id in list(db.scalars(select(User.id).where(User.deletion_approved_at <= cutoff))):
        # One account per transaction; skip_locked leaves an account a cancel is working on for the next run.
        user = db.scalar(
            select(User).where(User.id == user_id, User.deletion_approved_at <= cutoff).with_for_update(skip_locked=True)
        )
        if user is None:
            continue  # cancelled meanwhile, or locked right now
        try:
            _check_deletable(db, user)
        except HTTPException as exc:
            # Things changed during the wait (e.g. the faculty member took on a thesis): keep the account.
            log.warning("Scheduled deletion of user %s cancelled: %s", user.id, exc.detail)
            user.deletion_requested_at = user.deletion_approved_at = user.deletion_reason = user.deletion_requested_by_id = None
        else:
            _delete(db, user)
            deleted += 1
        db.commit()
    return deleted
