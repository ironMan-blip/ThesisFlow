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


def session_stamp(password_hash: str, session_epoch: int) -> str:
    # Tokens carry this, so changing a password (e.g. ADMIN_PASSWORD) or logging out (bumps the epoch)
    # ends every older session of that person.
    return hashlib.sha256(f"{password_hash}:{session_epoch}".encode()).hexdigest()[:16]


def create_access_token(user_id: int, password_hash: str, session_epoch: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    claims = {"sub": str(user_id), "pw": session_stamp(password_hash, session_epoch), "exp": expire}
    return jwt.encode(claims, settings.jwt_secret, algorithm=ALGORITHM)


# Marks a browser that logged in to an account. It signs nobody in: it only gives that browser its own login
# rate-limit buckets, so someone guessing from the same IP can't lock the owner out (OWASP "device cookie").
DEVICE_COOKIE = "tf_device"
DEVICE_TTL = timedelta(days=180)


def create_device_token(account: str) -> str:
    return jwt.encode({"dev": account, "exp": datetime.now(timezone.utc) + DEVICE_TTL}, settings.jwt_secret, algorithm=ALGORITHM)


def device_account(token: str | None) -> str | None:
    """The account a device cookie was issued for, or None. Access tokens have no "dev", so they never pass."""
    if not token:
        return None
    try:
        return str(jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "dev"]})["dev"])
    except jwt.PyJWTError:
        return None


def decode_access_token(token: str) -> tuple[int, str] | None:
    """(user id, password stamp), or None for a bad or expired token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp"]})
        return int(payload["sub"]), str(payload["pw"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
