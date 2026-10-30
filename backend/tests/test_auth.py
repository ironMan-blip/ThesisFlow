def register(client, email="a@b.com", password="password123"):
    return client.post("/api/auth/register", json={"email": email, "full_name": "A", "password": password})


def login(client, email="a@b.com", password="password123"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_register_login_me(client):
    assert register(client).status_code == 201
    token = login(client).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"
    assert me.json()["tools"] == ["proposal", "deadlines"]


def test_duplicate_email_rejected(client):
    register(client)
    assert register(client, email="A@B.com").status_code == 409


def test_wrong_password_rejected(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_works_for_seeded_reserved_domain(client, db):
    from app.models.user import Role
    from app.services import auth_service

    auth_service.create_user(db, "student@thesisflow.test", "S", "password123", Role.student)
    token = login(client, email="student@thesisflow.test").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "student@thesisflow.test"


def test_coordinator_signup_rejected(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "c@b.com", "full_name": "C", "password": "password123", "role": "coordinator"},
    )
    assert r.status_code == 422


def test_faculty_waits_for_approval(client, db):
    from app.models.user import Role
    from tests.helpers import auth

    r = client.post(
        "/api/auth/register", json={"email": "f@b.com", "full_name": "F", "password": "password123", "role": "faculty"}
    )
    assert r.status_code == 201 and r.json()["approved"] is False
    assert login(client, email="f@b.com").status_code == 403

    coord = auth(client, db, "coord@b.com", Role.coordinator)
    student = auth(client, db, "s@b.com")
    assert client.get("/api/auth/faculty-requests", headers=student).status_code == 403
    pending = client.get("/api/auth/faculty-requests", headers=coord).json()
    assert [p["email"] for p in pending] == ["f@b.com"]

    uid = pending[0]["id"]
    assert client.post(f"/api/auth/faculty-requests/{uid}/approve", headers=coord).status_code == 200
    assert login(client, email="f@b.com").status_code == 200
    assert client.get("/api/auth/faculty-requests", headers=coord).json() == []
    # Already approved, so no longer a request.
    assert client.delete(f"/api/auth/faculty-requests/{uid}", headers=coord).status_code == 404


def test_reject_frees_email(client, db):
    from app.models.user import Role
    from tests.helpers import auth

    body = {"email": "f@b.com", "full_name": "F", "password": "password123", "role": "faculty"}
    uid = client.post("/api/auth/register", json=body).json()["id"]
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert client.delete(f"/api/auth/faculty-requests/{uid}", headers=coord).status_code == 204
    assert client.post("/api/auth/register", json=body).status_code == 201


def test_ensure_admin_creates_and_resets(client, db, monkeypatch):
    from app.config import settings
    from app.services import auth_service

    monkeypatch.setattr(settings, "admin_email", "Admin@B.com")
    monkeypatch.setattr(settings, "admin_password", "first-pass1")
    auth_service.ensure_admin(db)
    assert login(client, email="admin@b.com", password="first-pass1").status_code == 200

    monkeypatch.setattr(settings, "admin_password", "second-pass2")
    auth_service.ensure_admin(db)
    assert login(client, email="admin@b.com", password="first-pass1").status_code == 401
    token = login(client, email="admin@b.com", password="second-pass2").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "coordinator"


def test_faculty_cannot_reregister_within_48_hours(client, db):
    from datetime import timedelta

    from app.models.user import User

    body = {"email": "f@b.com", "full_name": "F", "password": "password123", "role": "faculty"}
    old_id = client.post("/api/auth/register", json=body).json()["id"]
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 409
    assert "waiting for coordinator approval" in r.json()["detail"]

    # 48 hours pass without a decision: a new submission replaces the old one.
    user = db.get(User, old_id)
    user.created_at -= timedelta(hours=48, minutes=1)
    db.commit()
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    assert r.json()["id"] != old_id and db.get(User, old_id) is None
