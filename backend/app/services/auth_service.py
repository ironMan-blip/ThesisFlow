from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import Role, User
from app.schemas.user import UserCreate
from app.security import create_access_token, hash_password, verify_password


def register_student(db: Session, data: UserCreate) -> User:
    # Self sign-up is for students only. Faculty and coordinator accounts
    # are created by the coordinator (or by `python -m app.seed` in dev).
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        full_name=data.full_name,
        password_hash=hash_password(data.password),
        role=Role.student,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(db: Session, email: str, password: str) -> str:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return create_access_token(user.id)
