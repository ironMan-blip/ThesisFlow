from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import rate_limit
from app.config import settings
from app.models.milestone import Phase
from app.models.user import REVIEW_HOURS, REVIEW_WINDOW, Role, User
from app.schemas.user import MAX_PASSWORD, UserCreate
from app.security import create_access_token, hash_password, verify_password

_DUMMY_HASH = hash_password("timing-equaliser")
REGISTER_TAKEN = (
    "This ID number or email can't be registered. If you already have an account or applied, log in or contact the coordinator"
)


def get_by_email(db: Session, email: str) -> User | None:
    # Emails are stored lowercase, so every lookup goes through here.
    return db.scalar(select(User).where(User.email == email.lower()))


def get_by_id_number(db: Session, id_number: str) -> User | None:
    return db.scalar(select(User).where(User.id_number == id_number))


def get_by_initials(db: Session, initials: str) -> User | None:
    return db.scalar(select(User).where(User.initials == initials))


def create_user(
    db: Session, email: str, id_number: str, full_name: str, password: str, role: Role, approved: bool = True,
    initials: str | None = None,
) -> User:
    if get_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    if get_by_id_number(db, id_number):
        raise HTTPException(status.HTTP_409_CONFLICT, "ID number already registered")
    if initials and get_by_initials(db, initials):
        raise HTTPException(status.HTTP_409_CONFLICT, "Initials already registered")
    user = User(
        email=email.lower(),
        id_number=id_number,
        full_name=full_name,
        initials=initials,
        password_hash=hash_password(password),
        role=role,
        approved=approved,
        phase=Phase.P1 if role == Role.student else None,  # every student starts at P1
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # A parallel sign-up took the same email, ID number or initials after the checks above.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Email, ID number or initials already registered, try again")
    db.refresh(user)
    return user


def register(db: Session, data: UserCreate) -> User:
    # Every sign-up waits for the coordinator to approve before the user can log in.
    now = datetime.now(timezone.utc)
    existing = {u.id: u for u in (get_by_id_number(db, data.id_number), get_by_email(db, data.email)) if u}
    if any(u.approved or now < u.created_at + REVIEW_WINDOW for u in existing.values()):
        # One message for every clash, so sign-up can't be used to find out which IDs or emails have accounts.
        raise HTTPException(status.HTTP_409_CONFLICT, REGISTER_TAKEN)
    for u in existing.values():
        # The review window ran out: the new submission replaces the old request.
        db.delete(u)
    db.flush()
    # A request nobody reviewed within the window stops reserving its initials.
    holder = data.initials and get_by_initials(db, data.initials)
    if holder and not holder.approved and now >= holder.created_at + REVIEW_WINDOW:
        db.delete(holder)
        db.flush()
    return create_user(
        db, data.email, data.id_number, data.full_name, data.password, data.role, approved=False, initials=data.initials
    )


def ensure_admin(db: Session) -> User:
    """Make the single coordinator account match ADMIN_NAME / ADMIN_EMAIL / ADMIN_ID_NUMBER / ADMIN_PASSWORD. Runs at startup."""
    # Found by role, not ID or email, so changing either renames the one account instead of adding a second.
    user = db.scalars(select(User).where(User.role == Role.coordinator).order_by(User.id)).first()
    if user is None:
        return create_user(
            db, settings.admin_email, settings.admin_id_number, settings.admin_name, settings.admin_password, Role.coordinator
        )
    email = settings.admin_email.lower()
    for other in (get_by_id_number(db, settings.admin_id_number), get_by_email(db, email)):
        if other is not None and other.id != user.id:
            raise RuntimeError(f"ADMIN_ID_NUMBER / ADMIN_EMAIL already belong to another account (id {other.id})")
    user.approved, user.email, user.id_number, user.full_name = True, email, settings.admin_id_number, settings.admin_name
    if not verify_password(settings.admin_password, user.password_hash):
        user.password_hash = hash_password(settings.admin_password)
    db.commit()
    return user


def login(db: Session, id_number: str, password: str, ip: str) -> str:
    # Per account, not just per IP: stops guessing one password from many IPs or behind one shared IP.
    # Only failed logins count (a right one is taken back), and recorded before hashing so parallel guesses can't slip past.
    account = id_number[:32]
    keys = [(("login", account, ip), rate_limit.LOGIN_PER_ACCOUNT)]
    if not rate_limit.is_known_ip(account, ip):
        keys.append((("login", account), rate_limit.LOGIN_PER_ACCOUNT_ALL_IPS))
    for i, (key, limit) in enumerate(keys):
        if retry := rate_limit.hit(key, limit):
            for done, _ in keys[:i]:
                rate_limit.unhit(done)
            raise rate_limit.too_many(retry)
    # Sign-up caps passwords at MAX_PASSWORD, so a longer one can't be right; skip hashing a huge input.
    user = get_by_id_number(db, id_number) if len(password) <= MAX_PASSWORD else None
    # Hash even for unknown IDs so response time doesn't reveal which IDs exist.
    if not verify_password(password[:MAX_PASSWORD], user.password_hash if user else _DUMMY_HASH) or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong ID number or password")
    for key, _ in keys:
        rate_limit.unhit(key)
    if not user.approved:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"Your account is waiting for coordinator approval (within {REVIEW_HOURS} hours)"
        )
    rate_limit.remember_ip(account, ip)
    return create_access_token(user.id, user.password_hash, user.session_epoch)


def logout_everywhere(db: Session, user: User) -> None:
    # Bumped in SQL, so two logouts at once both count; every token issued before this stops working.
    db.execute(update(User).where(User.id == user.id).values(session_epoch=User.session_epoch + 1))
    db.commit()
