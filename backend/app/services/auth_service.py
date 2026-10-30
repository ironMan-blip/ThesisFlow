from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import REVIEW_WINDOW, Role, User
from app.schemas.user import UserCreate
from app.security import create_access_token, hash_password, verify_password
from app.services import proposal_service


def get_by_email(db: Session, email: str) -> User | None:
    # Emails are stored lowercase, so every lookup goes through here.
    return db.scalar(select(User).where(User.email == email.lower()))


def create_user(db: Session, email: str, full_name: str, password: str, role: Role, approved: bool = True) -> User:
    if get_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    user = User(
        email=email.lower(), full_name=full_name, password_hash=hash_password(password), role=role, approved=approved
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register(db: Session, data: UserCreate) -> User:
    # Students can log in right away; faculty wait for the coordinator to approve.
    existing = get_by_email(db, data.email)
    if existing and existing.role == Role.faculty and not existing.approved:
        retry_at = existing.created_at + REVIEW_WINDOW
        if datetime.now(timezone.utc) < retry_at:
            raise HTTPException(status.HTTP_409_CONFLICT, "User already applied to register, waiting for approval")
        # The review window ran out: the new submission replaces the old request.
        db.delete(existing)
        db.flush()
    return create_user(db, data.email, data.full_name, data.password, data.role, approved=data.role == Role.student)


def ensure_admin(db: Session) -> User:
    """Make the single coordinator account match ADMIN_EMAIL / ADMIN_PASSWORD. Runs at startup."""
    user = get_by_email(db, settings.admin_email)
    if user is None:
        return create_user(db, settings.admin_email, "Coordinator", settings.admin_password, Role.coordinator)
    user.role, user.approved = Role.coordinator, True
    if not verify_password(settings.admin_password, user.password_hash):
        user.password_hash = hash_password(settings.admin_password)
    db.commit()
    return user


def pending_faculty(db: Session) -> list[User]:
    return list(
        db.scalars(select(User).where(User.role == Role.faculty, User.approved.is_(False)).order_by(User.created_at))
    )


def _pending(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or user.role != Role.faculty or user.approved:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No pending faculty request with that id")
    return user


def approve_faculty(db: Session, user_id: int) -> User:
    user = _pending(db, user_id)
    user.approved = True
    db.commit()
    db.refresh(user)
    return user


def reject_faculty(db: Session, user_id: int) -> None:
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
    user = _deletion_pending(db, user_id)
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


def login(db: Session, email: str, password: str) -> str:
    user = get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    if not user.approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Your faculty account is waiting for coordinator approval (within 48 hours)"
        )
    return create_access_token(user.id)
