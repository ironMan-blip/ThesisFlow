"""Requests the coordinator decides (sign-ups and account deletions), plus the coordinator's account list."""

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import REVIEW_WINDOW, Role, User
from app.services import proposal_service


def pending_registrations(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.approved.is_(False)).order_by(User.created_at)))


def _pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending registration request with that id")
    return user


def approve_registration(db: Session, user_id: int) -> User:
    user = _pending(db, user_id)
    user.approved = True
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
    since = datetime.now(timezone.utc) - REVIEW_WINDOW
    return list(
        db.scalars(select(User).where(User.deletion_requested_at > since).order_by(User.deletion_requested_at))
    )


def _deletion_pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not user.deletion_pending:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending deletion request with that id")
    return user


def approve_deletion(db: Session, user_id: int) -> None:
    _delete(db, _deletion_pending(db, user_id))


def list_accounts(db: Session) -> list[User]:
    # Unapproved sign-ups are not accounts yet; they live in pending_registrations.
    # The coordinator is the admin login, not a member account.
    return list(db.scalars(
        select(User).where(User.approved.is_(True), User.role != Role.coordinator).order_by(User.role, User.full_name)
    ))


def delete_account(db: Session, user_id: int) -> None:
    user = db.get(User, user_id)
    if user is None or not user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that id")
    if user.role == Role.coordinator:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "The coordinator account cannot be deleted")
    _delete(db, user)


def _delete(db: Session, user: User) -> None:
    files = proposal_service.delete_owned(db, user)
    db.delete(user)
    db.commit()
    # Files go only after the rows are gone, so a failed commit never loses a PDF.
    for path in files:
        path.unlink(missing_ok=True)


def reject_deletion(db: Session, user_id: int) -> User:
    user = _deletion_pending(db, user_id)
    user.deletion_requested_at = None
    db.commit()
    db.refresh(user)
    return user
