"""Create one dev account per role. Run: docker compose exec backend python -m app.seed

Dev only. All accounts use the password "password123".
"""

from sqlalchemy import select

from app.database import SessionLocal
from app.models.user import Role, User
from app.security import hash_password

ACCOUNTS = [
    ("student@thesisflow.test", "Demo Student", Role.student),
    ("faculty@thesisflow.test", "Demo Faculty", Role.faculty),
    ("coordinator@thesisflow.test", "Demo Coordinator", Role.coordinator),
]


def main():
    with SessionLocal() as db:
        for email, name, role in ACCOUNTS:
            if db.scalar(select(User).where(User.email == email)):
                continue
            db.add(User(email=email, full_name=name, role=role, password_hash=hash_password("password123")))
            print(f"created {email}")
        db.commit()


if __name__ == "__main__":
    main()
