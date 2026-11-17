import io
from datetime import datetime, timedelta, timezone
from itertools import count

from pypdf import PdfWriter
from sqlalchemy import update

from app.models.group import MIN_MEMBERS, Group, GroupMember
from app.models.semester import Semester
from app.models.user import DELETION_DELAY, Role, User
from app.services import account_service, auth_service, group_service



def make_pdf(change=None) -> bytes:
    """A real one-page PDF; change(writer) can add to it first."""
    writer = PdfWriter()
    writer.add_blank_page(72, 72)
    if change:
        change(writer)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


PDF = make_pdf()
REASON = {"reason": "I uploaded the wrong file by mistake and it holds private data."}


_id_numbers = count(50000000)


def auth(client, db, email, role=Role.student):
    id_number = str(next(_id_numbers))
    auth_service.create_user(db, email, id_number, "U", "Password123", role)
    token = client.post("/api/auth/login", data={"username": id_number, "password": "Password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def me(client, headers):
    return client.get("/api/auth/me", headers=headers).json()


def make_group(client, db, student, size=MIN_MEMBERS):
    """Put the student in a student group with size - 1 new teammates, unless they are in one already. Returns it."""
    lead = db.get(User, me(client, student)["id"])
    if member := group_service.membership(db, lead.id):
        return member.group
    group = Group(name="Team", leader=lead)
    group.members.append(GroupMember(user=lead))
    for _ in range(size - 1):
        n = next(_id_numbers)
        group.members.append(GroupMember(user=auth_service.create_user(db, f"m{n}@x.com", str(n), "M", "Password123", Role.student)))
    db.add(group)
    db.flush()
    return group


def ask_supervisor(client, db, student, supervisor):
    """The student's group (made here if needed) asks the supervisor."""
    make_group(client, db, student)
    return client.post("/api/theses/mine", headers=student, json={"supervisor_id": me(client, supervisor)["id"]})


def form_group(client, db, student, supervisor=None):
    """Student's group asks a supervisor (made here unless given) and the supervisor accepts. Returns the supervisor's headers."""
    supervisor = supervisor or auth(client, db, f"sup{next(_id_numbers)}@x.com", Role.faculty)
    make_group(client, db, student)
    res = client.post("/api/theses/mine", headers=student, json={"supervisor_id": me(client, supervisor)["id"]})
    assert res.status_code == 201, res.json()
    tid = res.json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=supervisor).status_code == 204
    return supervisor


def supervised_student(client, db, email):
    """A student with an active thesis group registered for P1, ready to upload, and their supervisor's headers."""
    h = auth(client, db, email)
    sup = form_group(client, db, h)
    assert client.post("/api/theses/mine/register", headers=h).status_code == 200
    return h, sup


def student(client, db, email):
    """A student with an active thesis group registered for P1, ready to upload."""
    return supervised_student(client, db, email)[0]


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
    """Move every approved account delete past its 7-day wait, then run the deletion job like the background loop does."""
    db.execute(update(User).values(deletion_approved_at=User.deletion_approved_at - DELETION_DELAY))
    db.flush()
    db.expire_all()
    return account_service.run_due_deletions(db)
