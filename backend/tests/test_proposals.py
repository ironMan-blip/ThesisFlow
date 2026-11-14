from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.milestone import MilestoneTemplate, Phase
from app.models.user import Role
from tests.helpers import PDF, auth, me, student, upload

pytestmark = pytest.mark.usefixtures("timelines")


def test_each_upload_is_a_new_version_and_old_ones_stay(client, db):
    h = student(client, db, "s@x.com")
    empty = client.get("/api/proposals/mine", headers=h).json()
    assert (empty["versions"], empty["phase"], empty["upload_block"]) == ([], "P1", None)
    assert empty["thesis_code"].startswith("TH-")

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
    h = student(client, db, "s@x.com")
    assert upload(client, h, content=b"hello").status_code == 422
    assert upload(client, h, title="  ").status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    assert upload(client, h, content=PDF + b"x" * 1024 * 1024).status_code == 413
    # Far over the limit: refused from Content-Length before the body is read.
    res = upload(client, h, content=PDF + b"x" * 3 * 1024 * 1024)
    assert (res.status_code, res.json()["detail"]) == (413, "Upload is larger than 1 MB")
    assert client.get("/api/proposals/mine", headers=h).json()["versions"] == []


def test_upload_needs_an_accepted_thesis_group(client, db):
    h = auth(client, db, "s@x.com")
    res = upload(client, h)
    assert (res.status_code, res.json()["detail"]) == (409, "Form a thesis group first: choose a supervisor on the Thesis page")
    sup = auth(client, db, "f@x.com", Role.faculty)
    client.post("/api/theses/mine", headers=h, json={"supervisor_id": client.get("/api/auth/me", headers=sup).json()["id"]})
    res = upload(client, h)
    assert (res.status_code, res.json()["detail"]) == (409, "Your supervisor has not accepted your thesis group yet")


def test_only_the_student_and_their_supervisors_see_versions(client, db):
    owner = student(client, db, "s@x.com")
    other = student(client, db, "o@x.com")
    other_faculty = auth(client, db, "f@x.com", Role.faculty)
    coord = auth(client, db, "c@x.com", Role.coordinator)
    vid = upload(client, owner).json()["versions"][0]["id"]
    assert len(client.get("/api/theses", headers=coord).json()) == 2

    assert client.get(f"/api/proposals/versions/{vid}/file", headers=other).status_code == 404
    assert client.get(f"/api/proposals/versions/{vid}/file", headers=other_faculty).status_code == 404
    assert client.get(f"/api/proposals/versions/{vid}/file", headers=coord).status_code == 200


def test_group_members_and_coordinator_download_but_only_the_student_uploads(client, db):
    owner = auth(client, db, "s@x.com")
    sup, co = auth(client, db, "f1@x.com", Role.faculty), auth(client, db, "f2@x.com", Role.faculty)
    coord = auth(client, db, "c@x.com", Role.coordinator)
    body = {"supervisor_id": me(client, sup)["id"], "co_supervisor_id": me(client, co)["id"]}
    tid = client.post("/api/theses/mine", headers=owner, json=body).json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=sup).status_code == 204
    assert client.post("/api/theses/mine/register", headers=owner).status_code == 200
    vid = upload(client, owner).json()["versions"][0]["id"]
    file = lambda h: client.get(f"/api/proposals/versions/{vid}/file", headers=h).status_code

    assert (file(owner), file(sup), file(coord)) == (200, 200, 200)
    assert file(co) == 404  # not a group member until they accept
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=co).status_code == 204
    assert file(co) == 200
    assert [t["id"] for t in client.get("/api/theses", headers=co).json()] == [tid]
    for h in (sup, co, coord):
        assert upload(client, h).status_code == 403


def test_only_students_upload(client, db):
    faculty = auth(client, db, "f@x.com", Role.faculty)
    assert upload(client, faculty).status_code == 403


def test_owner_can_remove_a_version(client, db, tmp_path):
    owner = student(client, db, "s@x.com")
    other = student(client, db, "o@x.com")
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
    h = student(client, db, "s@x.com")
    for t in ("a", "b", "c"):
        upload(client, h, content=PDF + t.encode(), title=t)
    c, b, a = client.get("/api/proposals/mine", headers=h).json()["versions"]

    versions = client.delete(f"/api/proposals/versions/{a['id']}", headers=h).json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("c", 2), ("b", 1)]
    versions = upload(client, h, content=PDF + b"d", title="d").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("d", 3), ("c", 2), ("b", 1)]


def test_resubmitting_identical_upload_moves_it_to_latest(client, db, tmp_path):
    h = student(client, db, "s@x.com")
    for t in ("a", "b", "c"):
        upload(client, h, content=PDF + t.encode(), title=t)
    a_id = client.get("/api/proposals/mine", headers=h).json()["versions"][2]["id"]

    res = upload(client, h, content=PDF + b"a", title="a")
    assert res.status_code == 201
    versions = res.json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("a", 3), ("c", 2), ("b", 1)]
    assert (versions[0]["id"], versions[0]["is_latest"]) == (a_id, True)
    assert len(list((tmp_path / "proposals").iterdir())) == 3
    assert client.get(f"/api/proposals/versions/{a_id}/file", headers=h).content == PDF + b"a"

    # Re-submitting the current latest keeps the order.
    versions = upload(client, h, content=PDF + b"a", title="a").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("a", 3), ("c", 2), ("b", 1)]


def test_same_pdf_with_new_title_or_abstract_is_a_new_version(client, db):
    h = student(client, db, "s@x.com")
    upload(client, h, title="a")
    upload(client, h, title="a renamed")
    res = client.post(
        "/api/proposals/mine/versions",
        headers=h,
        data={"title": "a renamed", "abstract": "New abstract"},
        files={"file": ("p.pdf", PDF, "application/pdf")},
    )
    versions = res.json()["versions"]
    assert [(v["title"], v["abstract"], v["version_no"]) for v in versions] == [
        ("a renamed", "New abstract", 3),
        ("a renamed", "About it", 2),
        ("a", "About it", 1),
    ]


def test_upload_needs_the_phase_timeline(client, db):
    h = student(client, db, "s@x.com")
    db.delete(db.get(MilestoneTemplate, Phase.P1))
    db.flush()
    mine = client.get("/api/proposals/mine", headers=h).json()
    assert mine["upload_block"] == "The P1 timeline is not set yet"
    res = upload(client, h)
    assert (res.status_code, res.json()["detail"]) == (409, "The P1 timeline is not set yet")


def test_grace_period_warns_and_then_uploads_close(client, db):
    h = student(client, db, "s@x.com")
    p1 = db.get(MilestoneTemplate, Phase.P1)
    p1.due_at, p1.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 1  # past due, still in grace
    db.flush()
    mine = client.get("/api/proposals/mine", headers=h).json()
    assert mine["upload_block"] is None and mine["freeze_at"] is not None  # warning: upload or be frozen
    v = upload(client, h).json()["versions"][0]
    assert client.get("/api/proposals/mine", headers=h).json()["freeze_at"] is None  # submitted (late)

    p1.grace_days = 0  # grace over
    db.flush()
    mine = client.get("/api/proposals/mine", headers=h).json()
    assert mine["upload_block"] == "The P1 deadline and grace period have passed"
    assert mine["versions"][0]["can_delete"] is False  # a final submission
    res = client.delete(f"/api/proposals/versions/{v['id']}", headers=h)
    assert (res.status_code, res.json()["detail"]) == (409, "This version is a final submission, so it can't be removed")
