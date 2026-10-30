from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import REVIEW_WINDOW, Role, User
from app.schemas.user import UserCreate
from app.security import create_access_token, hash_password, verify_password


def get_by_email(db: Session, email: str) -> User | None:
    # Emails are stored lowercase, so every lookup goes through here.
    return db.scalar(select(User).where(User.email == email.lower()))


def get_by_id_number(db: Session, id_number: str) -> User | None:
    return db.scalar(select(User).where(User.id_number == id_number))


def create_user(
    db: Session, email: str, id_number: str, full_name: str, password: str, role: Role, approved: bool = True,
    initials: str | None = None,
) -> User:
    if get_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    if get_by_id_number(db, id_number):
        raise HTTPException(status.HTTP_409_CONFLICT, "ID number already registered")
    if initials and db.scalar(select(User).where(User.initials == initials)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Initials already registered")
    user = User(
        email=email.lower(),
        id_number=id_number,
        full_name=full_name,
        initials=initials,
        password_hash=hash_password(password),
        role=role,
        approved=approved,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register(db: Session, data: UserCreate) -> User:
    # Every sign-up waits for the coordinator to approve before the user can log in.
    existing = get_by_id_number(db, data.id_number) or get_by_email(db, data.email)
    if existing and not existing.approved:
        retry_at = existing.created_at + REVIEW_WINDOW
        if datetime.now(timezone.utc) < retry_at:
            raise HTTPException(status.HTTP_409_CONFLICT, "User already applied to register, waiting for approval")
        # The review window ran out: the new submission replaces the old request.
        db.delete(existing)
        db.flush()
    return create_user(
        db, data.email, data.id_number, data.full_name, data.password, data.role, approved=False, initials=data.initials
    )


def ensure_admin(db: Session) -> User:
    """Make the single coordinator account match ADMIN_EMAIL / ADMIN_ID_NUMBER / ADMIN_PASSWORD. Runs at startup."""
    user = get_by_email(db, settings.admin_email)
    if user is None:
        return create_user(
            db, settings.admin_email, settings.admin_id_number, "ironMan", settings.admin_password, Role.coordinator
        )
    user.role, user.approved, user.id_number, user.full_name = Role.coordinator, True, settings.admin_id_number, "ironMan"
    if not verify_password(settings.admin_password, user.password_hash):
        user.password_hash = hash_password(settings.admin_password)
    db.commit()
    return user


def login(db: Session, id_number: str, password: str) -> str:
    user = get_by_id_number(db, id_number)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong ID number or password")
    if not user.approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Your account is waiting for coordinator approval (within 48 hours)"
        )
    return create_access_token(user.id)
