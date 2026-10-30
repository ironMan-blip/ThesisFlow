from app.models.user import Role
from app.services import auth_service

PDF = b"%PDF-1.4\n% test\n"


def auth(client, db, email, role=Role.student):
    auth_service.create_user(db, email, "U", "password123", role)
    token = client.post("/api/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, content=PDF, title="My thesis", name="p.pdf", phase="P1"):
    return client.post(
        "/api/proposals/mine/versions",
        headers=headers,
        data={"phase": phase, "title": title, "abstract": "About it"},
        files={"file": (name, content, "application/pdf")},
    )
