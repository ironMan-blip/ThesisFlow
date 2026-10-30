from datetime import timedelta

from app.config import settings
from app.models.user import Role, User
from app.services import auth_service
from tests.helpers import auth, upload


def register(client, email="a@b.com", password="Password123", id_number="123456", role="student"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "id_number": id_number, "full_name": "A", "password": password, "role": role},
    )


def login(client, id_number="123456", password="Password123"):
    return client.post("/api/auth/login", data={"username": id_number, "password": password})


def test_register_login_me(client):
    assert register(client).status_code == 201
    token = login(client).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"
    assert me.json()["tools"] == ["proposal", "deadlines", "account"]


def test_duplicate_email_rejected(client):
    register(client)
    r = register(client, email="A@B.com", id_number="654321")
    assert r.status_code == 409
    assert r.json()["detail"] == "User already exists"
    # Same email under the other role is also taken.
    r = register(client, id_number="654321", role="faculty")
    assert r.status_code == 409
    assert r.json()["detail"] == "User already exists"


def test_duplicate_id_number_rejected(client):
    register(client)
    for role in ["student", "faculty"]:
        r = register(client, email="other@b.com", role=role)
        assert r.status_code == 409
        assert r.json()["detail"] == "ID number already registered"


def test_login_needs_id_number_not_email(client):
    register(client)
    assert login(client, id_number="a@b.com").status_code == 401
    assert login(client, id_number="999999").status_code == 401


def test_wrong_password_rejected(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_works_for_seeded_reserved_domain(client, db):
    auth_service.create_user(db, "student@thesisflow.test", "100001", "S", "Password123", Role.student)
    token = login(client, id_number="100001").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "student@thesisflow.test"


def test_coordinator_signup_rejected(client):
    assert register(client, role="coordinator").status_code == 422


def test_faculty_waits_for_approval(client, db):
    r = register(client, email="f@b.com", role="faculty")
    assert r.status_code == 201 and r.json()["approved"] is False
    assert login(client).status_code == 403

    coord = auth(client, db, "coord@b.com", Role.coordinator)
    student = auth(client, db, "s@b.com")
    assert client.get("/api/auth/faculty-requests", headers=student).status_code == 403
    pending = client.get("/api/auth/faculty-requests", headers=coord).json()
    assert [p["email"] for p in pending] == ["f@b.com"]

    uid = pending[0]["id"]
    assert client.post(f"/api/auth/faculty-requests/{uid}/approve", headers=coord).status_code == 200
    assert login(client).status_code == 200
    assert client.get("/api/auth/faculty-requests", headers=coord).json() == []
    # Already approved, so no longer a request.
    assert client.delete(f"/api/auth/faculty-requests/{uid}", headers=coord).status_code == 404


def test_reject_frees_email(client, db):
    body = {"email": "f@b.com", "id_number": "222222", "full_name": "F", "password": "Password123", "role": "faculty"}
    uid = client.post("/api/auth/register", json=body).json()["id"]
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert client.delete(f"/api/auth/faculty-requests/{uid}", headers=coord).status_code == 204
    assert client.post("/api/auth/register", json=body).status_code == 201


def test_ensure_admin_creates_and_resets(client, db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "Admin@B.com")
    monkeypatch.setattr(settings, "admin_id_number", "000000")
    monkeypatch.setattr(settings, "admin_password", "first-pass1")
    auth_service.ensure_admin(db)
    assert login(client, id_number="000000", password="first-pass1").status_code == 200

    monkeypatch.setattr(settings, "admin_id_number", "000009")
    monkeypatch.setattr(settings, "admin_password", "second-pass2")
    auth_service.ensure_admin(db)
    assert login(client, id_number="000009", password="first-pass1").status_code == 401
    token = login(client, id_number="000009", password="second-pass2").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "coordinator"


def test_faculty_cannot_reregister_within_48_hours(client, db):
    body = {"email": "f@b.com", "id_number": "222222", "full_name": "F", "password": "Password123", "role": "faculty"}
    old_id = client.post("/api/auth/register", json=body).json()["id"]
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 409
    assert r.json()["detail"] == "User already applied to register, waiting for approval"

    # 48 hours pass without a decision: a new submission replaces the old one.
    user = db.get(User, old_id)
    user.created_at -= timedelta(hours=48, minutes=1)
    db.commit()
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    assert r.json()["id"] != old_id and db.get(User, old_id) is None


def test_register_rejects_bad_email_and_weak_password(client):
    r = register(client, email="no-at-sign")
    assert r.status_code == 422
    assert r.json()["detail"].startswith("email:")
    for bad_id in ["12345", "1234567", "12a456", "１２３４５６"]:
        r = register(client, id_number=bad_id)
        assert r.status_code == 422, bad_id
        assert r.json()["detail"].startswith("id_number:"), bad_id
    for weak in ["Short1", "alllower123", "ALLUPPER123", "NoDigitsHere", "Has Space1"]:
        r = register(client, password=weak)
        assert r.status_code == 422, weak
        assert r.json()["detail"].startswith("password:"), weak


def test_account_deletion_needs_coordinator_approval(client, db, tmp_path):
    student = auth(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert upload(client, student).status_code == 201
    pdfs = list(tmp_path.rglob("*.pdf"))
    assert len(pdfs) == 1

    assert client.post("/api/auth/me/deletion-request", headers=coord).status_code == 403
    r = client.post("/api/auth/me/deletion-request", headers=student)
    assert r.status_code == 200 and r.json()["deletion_pending"] is True
    assert client.post("/api/auth/me/deletion-request", headers=student).status_code == 409
    # Still usable while waiting.
    assert client.get("/api/auth/me", headers=student).status_code == 200

    assert client.get("/api/auth/deletion-requests", headers=student).status_code == 403
    pending = client.get("/api/auth/deletion-requests", headers=coord).json()
    assert [p["email"] for p in pending] == ["s@b.com"]
    uid = pending[0]["id"]
    assert client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord).status_code == 204
    assert db.get(User, uid) is None
    assert not pdfs[0].exists()
    assert client.get("/api/auth/me", headers=student).status_code == 401


def test_reject_deletion_keeps_account(client, db):
    student = auth(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    uid = client.post("/api/auth/me/deletion-request", headers=student).json()["id"]
    r = client.delete(f"/api/auth/deletion-requests/{uid}", headers=coord)
    assert r.status_code == 200 and r.json()["deletion_pending"] is False
    assert client.get("/api/auth/deletion-requests", headers=coord).json() == []
    assert client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord).status_code == 404


def test_deletion_request_lapses_after_48_hours(client, db):
    student = auth(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    uid = client.post("/api/auth/me/deletion-request", headers=student).json()["id"]
    user = db.get(User, uid)
    user.deletion_requested_at -= timedelta(hours=48, minutes=1)
    db.commit()

    assert client.get("/api/auth/deletion-requests", headers=coord).json() == []
    assert client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord).status_code == 404
    assert db.get(User, uid) is not None
    me = client.get("/api/auth/me", headers=student).json()
    assert me["deletion_pending"] is False
    # The user may ask again.
    assert client.post("/api/auth/me/deletion-request", headers=student).status_code == 200
