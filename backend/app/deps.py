"""Shared FastAPI dependencies. Controllers use these to check the user."""

import hmac

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import Role, User
from app.security import decode_access_token, password_stamp

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    claims = decode_access_token(token)
    user = db.get(User, claims[0]) if claims else None
    # Unapproved accounts never get tokens; checked again so a future un-approve path can't leak access.
    if user is None or not user.approved or not hmac.compare_digest(claims[1], password_stamp(user.password_hash)):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return user


def require_roles(*roles: Role):
    """Usage: user: User = Depends(require_roles(Role.coordinator))"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed for your role")
        return user

    return checker
