"""Create one dev account per role. Run: docker compose exec backend python -m app.seed

Dev only. All accounts use the password "password123".
"""

from app.database import SessionLocal
from app.models.user import Role
from app.services import auth_service

ACCOUNTS = [
    ("student@thesisflow.test", "Demo Student", Role.student),
    ("faculty@thesisflow.test", "Demo Faculty", Role.faculty),
    ("coordinator@thesisflow.test", "Demo Coordinator", Role.coordinator),
]


def main():
    with SessionLocal() as db:
        for email, name, role in ACCOUNTS:
            if auth_service.get_by_email(db, email):
                continue
            auth_service.create_user(db, email, name, "password123", role)
            print(f"created {email}")


if __name__ == "__main__":
    main()
