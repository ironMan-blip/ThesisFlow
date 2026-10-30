from app.config import settings
from app.models.user import Role
from tests.helpers import PDF, auth, upload


def test_each_upload_is_a_new_version_and_old_ones_stay(client, db):
    h = auth(client, db, "s@x.com")
    empty = client.get("/api/proposals/mine", headers=h).json()
    assert (empty["versions"], empty["phases"]) == ([], ["P1", "P2", "P3"])

    assert upload(client, h, title="v1").status_code == 201
    res = upload(client, h, content=PDF + b"v2", title="v2", name="p2.pdf")
    assert res.status_code == 201
    versions = res.json()["versions"]
    assert [v["version_no"] for v in versions] == [2, 1]
    assert [v["title"] for v in versions] == ["v2", "v1"]
    assert [v["is_latest"] for v in versions] == [True, False]
    assert versions[0]["phase"] == "P1"
    assert versions[0]["size_label"].endswith(" KB")
    assert versions[0]["download_path"] == f"/proposals/versions/{versions[0]['id']}/file"

    old = client.get(f"/api/proposals/versions/{versions[1]['id']}/file", headers=h)
    assert old.status_code == 200
    assert old.content == PDF
    assert old.headers["content-type"] == "application/pdf"


def test_rejects_non_pdf_and_oversize(client, db, monkeypatch):
    h = auth(client, db, "s@x.com")
    assert upload(client, h, content=b"hello").status_code == 422
    assert upload(client, h, title="  ").status_code == 422
    assert upload(client, h, phase="P9").status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert upload(client, h, content=PDF + b"x" * 1024 * 1024).status_code == 413
    assert client.get("/api/proposals/mine", headers=h).json()["versions"] == []


def test_other_students_cannot_see_but_faculty_can(client, db):
    owner = auth(client, db, "s@x.com")
    other = auth(client, db, "o@x.com")
    faculty = auth(client, db, "f@x.com", Role.faculty)
    vid = upload(client, owner).json()["versions"][0]["id"]

    assert client.get(f"/api/proposals/versions/{vid}/file", headers=other).status_code == 404
    assert client.get(f"/api/proposals/versions/{vid}/file", headers=faculty).status_code == 200


def test_only_students_upload(client, db):
    faculty = auth(client, db, "f@x.com", Role.faculty)
    assert upload(client, faculty).status_code == 403


def test_owner_can_remove_a_version(client, db, tmp_path):
    owner = auth(client, db, "s@x.com")
    other = auth(client, db, "o@x.com")
    upload(client, owner, title="v1")
    v2, v1 = upload(client, owner, title="v2").json()["versions"]

    assert client.delete(f"/api/proposals/versions/{v1['id']}", headers=other).status_code == 404
    res = client.delete(f"/api/proposals/versions/{v1['id']}", headers=owner)
    assert res.status_code == 200
    assert [v["id"] for v in res.json()["versions"]] == [v2["id"]]
    assert len(list((tmp_path / "proposals").iterdir())) == 1
    assert client.get(f"/api/proposals/versions/{v1['id']}/file", headers=owner).status_code == 404
    assert client.delete(f"/api/proposals/versions/{v1['id']}", headers=owner).status_code == 404


def test_removing_a_version_renumbers_later_ones(client, db):
    h = auth(client, db, "s@x.com")
    for t in ("a", "b", "c"):
        upload(client, h, title=t)
    c, b, a = client.get("/api/proposals/mine", headers=h).json()["versions"]

    versions = client.delete(f"/api/proposals/versions/{a['id']}", headers=h).json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("c", 2), ("b", 1)]
    versions = upload(client, h, title="d").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("d", 3), ("c", 2), ("b", 1)]
