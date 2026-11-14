"""Requests the coordinator decides (sign-ups and account deletions), plus the coordinator's account list."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.thesis import ThesisStatus
from app.models.user import REVIEW_WINDOW, Role, User
from app.services import progress_service, thesis_service


def _registrations() -> Select:
    return select(User).where(User.approved.is_(False))


def _deletions() -> Select:
    return select(User).where(User.deletion_requested_at > datetime.now(timezone.utc) - REVIEW_WINDOW)


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
    # Deleting frees the email so the person can register again.
    db.delete(_pending(db, user_id))
    db.commit()


def request_deletion(db: Session, user: User) -> User:
    # The account stays usable until the coordinator approves; no decision in 48 hours means it is kept.
    if user.role == Role.coordinator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The coordinator account cannot be deleted")
    if user.deletion_pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Deletion already requested, waiting for the coordinator")
    user.deletion_requested_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    return user


def pending_deletions(db: Session) -> list[User]:
    return list(db.scalars(_deletions().order_by(User.deletion_requested_at)))


def _deletion_pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not user.deletion_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending deletion request with that id")
    return user


def approve_deletion(db: Session, user_id: int) -> None:
    _delete(db, _deletion_pending(db, user_id))


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


def delete_account(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None or not user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that id")
    _delete(db, user)


def _delete(db: Session, user: User) -> None:
    # The thesis and every proposal version stay as an archive; the foreign keys only clear the user.
    _check_deletable(db, user)
    thesis, user.thesis = user.thesis, None
    if thesis is not None and thesis.status == ThesisStatus.pending:
        db.delete(thesis)  # never accepted, so no thesis ID and no versions
    elif thesis is not None and thesis.status == ThesisStatus.active:
        thesis.status = ThesisStatus.dropped
    db.delete(user)
    db.commit()


def reject_deletion(db: Session, user_id: int) -> User:
    user = _deletion_pending(db, user_id)
    user.deletion_requested_at = None
    db.commit()
    db.refresh(user)
    return user
