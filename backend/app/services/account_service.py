"""Requests the coordinator decides (sign-ups), scheduled account deletions, and the coordinator's account list.

Deleting an account always takes DELETION_DELAY: the user (or the coordinator) asks with a reason, the account stays
usable meanwhile, only the coordinator can cancel, and run_due_deletions deletes it once the wait is over.
"""

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.thesis import ThesisStatus
from app.models.user import DELETION_DELAY, Role, User
from app.services import progress_service, proposal_service, thesis_service

log = logging.getLogger(__name__)


def _registrations() -> Select:
    return select(User).where(User.approved.is_(False))


def _deletions() -> Select:
    return select(User).where(User.deletion_requested_at.is_not(None))


def pending_registrations(db: Session) -> list[User]:
    return list(db.scalars(_registrations().order_by(User.created_at)))


def _pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.approved:
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


def _schedule(db: Session, user: User, by: User, reason: str) -> User:
    _check_deletable(db, user)
    if user.deletion_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account's deletion is already scheduled")
    user.deletion_requested_at, user.deletion_reason, user.deletion_requested_by_id = datetime.now(timezone.utc), reason, by.id
    db.commit()
    db.refresh(user)
    return user


def request_deletion(db: Session, user: User, reason: str) -> User:
    # The account stays usable until the deletion runs; the user can't take the request back, only the coordinator can.
    return _schedule(db, _locked(db, user.id), user, reason)


def schedule_deletion(db: Session, coordinator: User, user_id: int, reason: str) -> User:
    """Coordinator: delete an account. Same wait as a user's own request, so it can still be cancelled."""
    user = _locked(db, user_id)
    if user is None or not user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that id")
    return _schedule(db, user, coordinator, reason)


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
            status.HTTP_409_CONFLICT, "This faculty member supervises an active or requested thesis, so the account is kept"
        )


def pending_counts(db: Session, user: User) -> dict[str, int]:
    # Badge counts keyed by tool: the coordinator decides requests, faculty answer supervision requests.
    if user.role == Role.faculty:
        return {"theses": thesis_service.count_requests(db, user)}
    if user.role != Role.coordinator:
        return {}
    # Polled every 10s by the UI, so count in SQL instead of loading the rows.
    count = lambda q: db.scalar(q.with_only_columns(func.count()))
    return {
        "registration_requests": count(_registrations()),
        "deletion_requests": count(_deletions()),
        "restart_requests": progress_service.count_restarts(db),
        "version_delete_requests": proposal_service.count_delete_requests(db),
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
    thesis, user.thesis = user.thesis, None
    if thesis is not None and thesis.status == ThesisStatus.pending:
        db.delete(thesis)  # never accepted, so no thesis ID and no versions
    elif thesis is not None and thesis.status == ThesisStatus.active:
        thesis.status = ThesisStatus.dropped
    db.delete(user)


def cancel_deletion(db: Session, user_id: int) -> User:
    """Coordinator only, any time before the deletion runs."""
    user = _locked(db, user_id)
    if user is None or not user.deletion_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No scheduled deletion with that id")
    user.deletion_requested_at = user.deletion_reason = user.deletion_requested_by_id = None
    db.commit()
    db.refresh(user)
    return user


def run_due_deletions(db: Session, now: datetime | None = None) -> int:
    """Delete every account whose wait is over. Run by the background job in app.main. Returns how many went."""
    cutoff = (now or datetime.now(timezone.utc)) - DELETION_DELAY
    deleted = 0
    for user_id in list(db.scalars(select(User.id).where(User.deletion_requested_at <= cutoff))):
        # One account per transaction; skip_locked leaves an account a cancel is working on for the next run.
        user = db.scalar(
            select(User).where(User.id == user_id, User.deletion_requested_at <= cutoff).with_for_update(skip_locked=True)
        )
        if user is None:
            continue  # cancelled meanwhile, or locked right now
        try:
            _check_deletable(db, user)
        except HTTPException as exc:
            # Things changed during the wait (e.g. the faculty member took on a thesis): keep the account.
            log.warning("Scheduled deletion of user %s cancelled: %s", user.id, exc.detail)
            user.deletion_requested_at = user.deletion_reason = user.deletion_requested_by_id = None
        else:
            _delete(db, user)
            deleted += 1
        db.commit()
    return deleted
