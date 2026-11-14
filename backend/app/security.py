import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

from app.config import settings

ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hash.verify(password, hashed)


def password_stamp(password_hash: str) -> str:
    # Tokens carry this, so changing a password (e.g. ADMIN_PASSWORD) logs out every older session.
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_access_token(user_id: int, password_hash: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    claims = {"sub": str(user_id), "pw": password_stamp(password_hash), "exp": expire}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> tuple[int, str] | None:
    """(user id, password stamp), or None for a bad or expired token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
        return int(payload["sub"]), str(payload["pw"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
