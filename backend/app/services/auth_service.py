from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.security import create_access_token, hash_password, verify_password


def get_by_email(db: Session, email: str) -> User | None:
    # Emails are stored lowercase, so every lookup goes through here.
    return db.scalar(select(User).where(User.email == email.lower()))


def create_user(db: Session, email: str, full_name: str, password: str, role: Role) -> User:
    if get_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email.lower(), full_name=full_name, password_hash=hash_password(password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def register_student(db: Session, data: UserCreate) -> User:
    # Self sign-up is for students only. Faculty and coordinator accounts
    # are created by the coordinator (or by `python -m app.seed` in dev).
    return create_user(db, data.email, data.full_name, data.password, Role.student)


def login(db: Session, email: str, password: str) -> str:
    user = get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return create_access_token(user.id)
