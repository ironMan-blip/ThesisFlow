"""Create a dev student and faculty account. Run: docker compose exec backend python -m app.seed

Dev only. Both use the password "password123". The coordinator comes from ADMIN_EMAIL / ADMIN_ID_NUMBER / ADMIN_PASSWORD.
"""

from app.database import SessionLocal
from app.models.user import Role
from app.services import auth_service

ACCOUNTS = [
    ("student@thesisflow.test", "10000001", "Demo Student", Role.student, None),
    ("faculty@thesisflow.test", "20000001", "Demo Faculty", Role.faculty, "DF"),
]


def main():
    with SessionLocal() as db:
        for email, id_number, name, role, initials in ACCOUNTS:
            if auth_service.get_by_email(db, email):
                continue
            auth_service.create_user(db, email, id_number, name, "password123", role, initials=initials)
            print(f"created {email} (ID {id_number})")


if __name__ == "__main__":
    main()
