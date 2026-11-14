from itertools import count

from app.models.user import Role
from app.services import auth_service

PDF = b"%PDF-1.4\n% test\n"


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
    """A student with an active thesis group, ready to upload."""
    h = auth(client, db, email)
    form_group(client, db, h)
    return h


def upload(client, headers, content=PDF, title="My thesis", name="p.pdf"):
    return client.post(
        "/api/proposals/mine/versions",
        headers=headers,
        data={"title": title, "abstract": "About it"},
        files={"file": (name, content, "application/pdf")},
    )
