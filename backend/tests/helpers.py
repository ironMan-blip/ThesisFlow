from datetime import datetime, timedelta, timezone
from itertools import count

from sqlalchemy import update

from app.models.proposal import ProposalVersion
from app.models.semester import Semester
from app.models.user import DELETION_DELAY, Role, User
from app.services import account_service, auth_service, proposal_service

PDF = b"%PDF-1.4\n% test\n%%EOF\n"
REASON = {"reason": "I uploaded the wrong file by mistake and it holds private data."}


_id_numbers = count(50000000)


def auth(client, db, email, role=Role.student):
    id_number = str(next(_id_numbers))
    auth_service.create_user(db, email, id_number, "U", "Password123", role)
    token = client.post("/api/auth/login", data={"username": id_number, "password": "Password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def me(client, headers):
    return client.get("/api/auth/me", headers=headers).json()


def form_group(client, db, student, supervisor=None):
    """Student asks a supervisor (made here unless given) and the supervisor accepts. Returns the supervisor's headers."""
    supervisor = supervisor or auth(client, db, f"sup{next(_id_numbers)}@x.com", Role.faculty)
    res = client.post("/api/theses/mine", headers=student, json={"supervisor_id": me(client, supervisor)["id"]})
    assert res.status_code == 201, res.json()
    tid = res.json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=supervisor).status_code == 204
    return supervisor


def student(client, db, email):
    """A student with an active thesis group registered for P1, ready to upload."""
    h = auth(client, db, email)
    form_group(client, db, h)
    assert client.post("/api/theses/mine/register", headers=h).status_code == 200
    return h


def upload(client, headers, content=PDF, title="My thesis", name="p.pdf"):
    return client.post(
        "/api/proposals/mine/versions",
        headers=headers,
        data={"title": title, "abstract": "About it"},
        files={"file": (name, content, "application/pdf")},
    )


def close_registration(db):
    """Move the semester start a month back, so P1 registration is over and P1 deadlines can be in the past."""
    db.execute(update(Semester).values(started_at=datetime.now(timezone.utc) - timedelta(days=30)))
    db.flush()


def run_deletions_due(db):
    """Move every scheduled delete past its 7-day wait, then run the deletion job like the background loop does."""
    db.execute(update(User).values(deletion_requested_at=User.deletion_requested_at - DELETION_DELAY))
    db.execute(update(ProposalVersion).values(delete_requested_at=ProposalVersion.delete_requested_at - DELETION_DELAY))
    db.flush()
    db.expire_all()
    return account_service.run_due_deletions(db), proposal_service.run_due_deletions(db)
