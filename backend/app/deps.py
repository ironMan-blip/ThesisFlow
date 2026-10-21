"""Shared FastAPI dependencies. Controllers use these to check the user."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Role, User
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def require_roles(*roles: Role):
    """Usage: user: User = Depends(require_roles(Role.coordinator))"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return user

    return checker
