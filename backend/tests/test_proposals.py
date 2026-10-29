import pytest

from app.config import settings
from app.models.user import Role
from app.services import auth_service

PDF = b"%PDF-1.4\n% test\n"


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


def auth(client, db, email, role=Role.student):
    auth_service.create_user(db, email, "U", "password123", role)
    token = client.post("/api/auth/login", data={"username": email, "password": "password123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def upload(client, headers, content=PDF, title="My thesis", name="p.pdf"):
    return client.post(
        "/api/proposals/mine/versions",
        headers=headers,
        data={"title": title, "abstract": "About it"},
        files={"file": (name, content, "application/pdf")},
    )


def test_each_upload_is_a_new_version_and_old_ones_stay(client, db):
    h = auth(client, db, "s@x.com")
    assert client.get("/api/proposals/mine", headers=h).json() is None

    assert upload(client, h, title="v1").status_code == 201
    res = upload(client, h, content=PDF + b"v2", title="v2", name="p2.pdf")
    assert res.status_code == 201
    versions = res.json()["versions"]
    assert [v["version_no"] for v in versions] == [2, 1]
    assert [v["title"] for v in versions] == ["v2", "v1"]

    old = client.get(f"/api/proposals/versions/{versions[1]['id']}/file", headers=h)
    assert old.status_code == 200
    assert old.content == PDF
    assert old.headers["content-type"] == "application/pdf"


def test_rejects_non_pdf_and_oversize(client, db, monkeypatch):
    h = auth(client, db, "s@x.com")
    assert upload(client, h, content=b"hello").status_code == 422
    assert upload(client, h, title="  ").status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert upload(client, h, content=PDF + b"x" * 1024 * 1024).status_code == 413
    assert client.get("/api/proposals/mine", headers=h).json() is None


def test_other_students_cannot_see_but_faculty_can(client, db):
    owner = auth(client, db, "s@x.com")
    other = auth(client, db, "o@x.com")
    faculty = auth(client, db, "f@x.com", Role.faculty)
    proposal = upload(client, owner).json()
    vid = proposal["versions"][0]["id"]

    assert client.get(f"/api/proposals/{proposal['id']}", headers=other).status_code == 404
    assert client.get(f"/api/proposals/versions/{vid}/file", headers=other).status_code == 404
    assert client.get(f"/api/proposals/{proposal['id']}", headers=faculty).status_code == 200
    assert client.get(f"/api/proposals/versions/{vid}/file", headers=faculty).status_code == 200


def test_only_students_upload(client, db):
    faculty = auth(client, db, "f@x.com", Role.faculty)
    assert upload(client, faculty).status_code == 403
