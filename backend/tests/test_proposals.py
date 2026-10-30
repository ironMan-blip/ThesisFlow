from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.milestone import Milestone, Phase
from app.models.user import Role
from tests.helpers import PDF, auth, upload

pytestmark = pytest.mark.usefixtures("timelines")


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
    v2, v1 = upload(client, owner, content=PDF + b"v2", title="v2").json()["versions"]

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
        upload(client, h, content=PDF + t.encode(), title=t)
    c, b, a = client.get("/api/proposals/mine", headers=h).json()["versions"]

    versions = client.delete(f"/api/proposals/versions/{a['id']}", headers=h).json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("c", 2), ("b", 1)]
    versions = upload(client, h, content=PDF + b"d", title="d").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("d", 3), ("c", 2), ("b", 1)]


def test_resubmitting_identical_upload_moves_it_to_latest(client, db, tmp_path):
    h = auth(client, db, "s@x.com")
    for t in ("a", "b", "c"):
        upload(client, h, content=PDF + t.encode(), title=t)
    a_id = client.get("/api/proposals/mine", headers=h).json()["versions"][2]["id"]

    res = upload(client, h, content=PDF + b"a", title="a", phase="P2")
    assert res.status_code == 201
    versions = res.json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("a", 3), ("c", 2), ("b", 1)]
    assert (versions[0]["id"], versions[0]["phase"], versions[0]["is_latest"]) == (a_id, "P2", True)
    assert len(list((tmp_path / "proposals").iterdir())) == 3
    assert client.get(f"/api/proposals/versions/{a_id}/file", headers=h).content == PDF + b"a"

    # Re-submitting the current latest keeps the order.
    versions = upload(client, h, content=PDF + b"a", title="a").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("a", 3), ("c", 2), ("b", 1)]


def test_same_pdf_with_new_title_or_abstract_is_a_new_version(client, db):
    h = auth(client, db, "s@x.com")
    upload(client, h, title="a")
    upload(client, h, title="a renamed")
    res = client.post(
        "/api/proposals/mine/versions",
        headers=h,
        data={"phase": "P1", "title": "a renamed", "abstract": "New abstract"},
        files={"file": ("p.pdf", PDF, "application/pdf")},
    )
    versions = res.json()["versions"]
    assert [(v["title"], v["abstract"], v["version_no"]) for v in versions] == [
        ("a renamed", "New abstract", 3),
        ("a renamed", "About it", 2),
        ("a", "About it", 1),
    ]


def test_upload_needs_the_phase_timeline(client, db):
    h = auth(client, db, "s@x.com")
    db.delete(db.get(Milestone, Phase.P2))
    db.delete(db.get(Milestone, Phase.P3))
    db.flush()
    assert client.get("/api/proposals/mine", headers=h).json()["phases"] == ["P1"]
    res = upload(client, h, phase="P2")
    assert (res.status_code, res.json()["detail"]) == (409, "The P2 timeline is not set yet")
    assert upload(client, h, phase="P1").status_code == 201


def test_upload_closes_when_grace_period_ends(client, db):
    h = auth(client, db, "s@x.com")
    now = datetime.now(timezone.utc)
    db.get(Milestone, Phase.P1).due_at = now - timedelta(minutes=5)
    db.get(Milestone, Phase.P1).grace_minutes = 60  # past due, still in grace
    db.get(Milestone, Phase.P2).due_at = now - timedelta(minutes=5)  # no grace: closed
    db.flush()
    assert client.get("/api/proposals/mine", headers=h).json()["phases"] == ["P1"]  # P2 missed locks P3
    assert upload(client, h, phase="P1").status_code == 201
    res = upload(client, h, phase="P2")
    assert (res.status_code, res.json()["detail"]) == (409, "The P2 deadline and grace period have passed")


def test_missed_phase_locks_later_phases_until_new_semester(client, db):
    on_time, missed = auth(client, db, "a@x.com"), auth(client, db, "b@x.com")
    assert upload(client, on_time, phase="P1").status_code == 201
    p1 = db.get(Milestone, Phase.P1)
    p1.due_at = datetime.now(timezone.utc) - timedelta(minutes=5)  # P1 closes
    db.flush()

    assert client.get("/api/proposals/mine", headers=on_time).json()["phases"] == ["P2", "P3"]
    assert client.get("/api/proposals/mine", headers=missed).json()["phases"] == []
    res = upload(client, missed, phase="P2")
    assert (res.status_code, res.json()["detail"]) == (409, "You missed P1, so uploads are closed until the next semester")

    p1.due_at = datetime.now(timezone.utc) + timedelta(days=1)  # new semester: P1 open again
    db.flush()
    assert upload(client, missed, phase="P1").status_code == 201
