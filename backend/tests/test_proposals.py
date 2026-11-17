import re
from datetime import datetime, timedelta, timezone

import pytest
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from app import virus_scan
from app.config import settings
from app.models.milestone import MilestoneTemplate, Phase
from app.models.user import Role
from app.schemas.proposal import MAX_ABSTRACT_CHARS
from app.services import proposal_service
from tests.helpers import PDF, REASON, make_pdf, auth, me, student, supervised_student, upload

pytestmark = pytest.mark.usefixtures("timelines")


def test_each_upload_is_a_new_version_and_old_ones_stay(client, db):
    h = student(client, db, "s@x.com")
    empty = client.get("/api/proposals/mine", headers=h).json()
    assert (empty["versions"], empty["phase"], empty["upload_block"]) == ([], "P1", None)
    assert re.fullmatch(r"T\d{8}", empty["thesis_code"])

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


def test_rejects_overlong_abstract(client, db):
    h = student(client, db, "s@x.com")
    res = client.post(
        "/api/proposals/mine/versions",
        headers=h,
        data={"title": "T", "abstract": "a" * (MAX_ABSTRACT_CHARS + 1)},
        files={"file": ("p.pdf", PDF, "application/pdf")},
    )
    assert res.status_code == 422
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
    owner, sup = supervised_student(client, db, "s@x.com")
    other = student(client, db, "o@x.com")
    other_faculty = auth(client, db, "f@x.com", Role.faculty)
    coord = auth(client, db, "c@x.com", Role.coordinator)
    vid = upload(client, owner).json()["versions"][0]["id"]
    file = lambda h: client.get(f"/api/proposals/versions/{vid}/file", headers=h).status_code

    assert (file(owner), file(sup)) == (200, 200)
    assert (file(other), file(other_faculty)) == (404, 404)
    assert file(coord) == 404  # the coordinator runs semesters and accounts, never individual theses
    assert client.get("/api/theses", headers=coord).status_code == 403


def test_a_joined_co_supervisor_downloads_but_only_the_student_uploads(client, db):
    owner, sup = supervised_student(client, db, "s@x.com")
    co = auth(client, db, "co@x.com", Role.faculty)
    tid = client.get("/api/theses/mine", headers=owner).json()["thesis"]["id"]
    client.post("/api/theses/mine/co-supervisor", headers=owner, json={"co_supervisor_id": me(client, co)["id"]})
    vid = upload(client, owner).json()["versions"][0]["id"]
    file = lambda h: client.get(f"/api/proposals/versions/{vid}/file", headers=h).status_code
    assert file(co) == 404  # not in the group until both agree
    for f in (co, sup):
        assert client.post(f"/api/theses/requests/{tid}/accept", headers=f).status_code == 204
    assert (file(owner), file(sup), file(co)) == (200, 200, 200)
    for h in (sup, co, auth(client, db, "c@x.com", Role.coordinator)):
        assert upload(client, h).status_code == 403


def test_only_students_upload(client, db):
    faculty = auth(client, db, "f@x.com", Role.faculty)
    assert upload(client, faculty).status_code == 403


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
    assert [x["id"] for x in mine["versions"]] == [v["id"]]  # the submission is kept


def test_versions_cannot_be_deleted(client, db):
    # SRS F11: every upload is a new version and old ones are kept. Nobody can delete one, the supervisor included.
    h, sup = supervised_student(client, db, "s@x.com")
    v = upload(client, h).json()["versions"][0]
    vid = v["id"]
    for headers in (h, sup):
        assert client.delete(f"/api/proposals/versions/{vid}", headers=headers).status_code in (404, 405)
        assert client.post(f"/api/proposals/versions/{vid}/delete-request", headers=headers, json=REASON).status_code == 404
        assert client.post(f"/api/proposals/versions/{vid}/deletion", headers=headers, json=REASON).status_code == 404
        assert client.post(f"/api/proposals/delete-requests/{vid}/approve", headers=headers).status_code == 404
        assert client.delete(f"/api/proposals/delete-requests/{vid}", headers=headers).status_code == 404
        assert client.get(f"/api/proposals/versions/{vid}/file", headers=headers).status_code == 200
    assert not any("delete" in k for k in v)


def _open_action(writer, action):
    writer._root_object[NameObject("/OpenAction")] = DictionaryObject(
        {NameObject(k): NameObject(v) if v.startswith("/") else TextStringObject(v) for k, v in action.items()}
    )


def test_only_real_pdfs_without_active_content_are_stored(client, db, tmp_path):
    h = student(client, db, "s@x.com")
    assert upload(client, h, content=b"%PDF-1.4\nnot really a pdf\n%%EOF\n").status_code == 422
    assert upload(client, h, content=PDF + b"\n" * 100).status_code == 201  # trailing bytes after %%EOF are fine
    for bad in (
        make_pdf(lambda w: _open_action(w, {"/S": "/JavaScript", "/JS": "app.alert('hi')"})),
        make_pdf(lambda w: _open_action(w, {"/S": "/Launch", "/F": "calc.exe"})),
        make_pdf(lambda w: w.add_attachment("run.exe", b"MZ")),
        make_pdf(lambda w: w.encrypt("secret")),
    ):
        res = upload(client, h, content=bad)
        assert res.status_code == 422, res.json()
    assert len(client.get("/api/proposals/mine", headers=h).json()["versions"]) == 1
    assert len(list((tmp_path / "proposals").iterdir())) == 1  # refused files are not kept


def test_uploads_per_phase_are_capped(client, db, monkeypatch):
    monkeypatch.setattr(proposal_service, "MAX_VERSIONS_PER_PHASE", 2)
    h = student(client, db, "cap@b.com")
    assert upload(client, h, title="one").status_code == 201
    assert upload(client, h, title="two").status_code == 201
    r = upload(client, h, title="three")
    assert r.status_code == 409 and "2 versions" in r.json()["detail"]
    # Re-sending a stored version adds nothing, so it still works at the cap.
    assert upload(client, h, title="one").status_code == 201


def test_infected_uploads_are_refused_and_uploads_pause_without_a_scanner(client, db, tmp_path, monkeypatch):
    h = student(client, db, "s@x.com")
    monkeypatch.setattr(virus_scan, "scan", lambda path: "Win.Test.EICAR_HDB-1")
    res = upload(client, h)
    assert res.status_code == 422 and "Win.Test.EICAR_HDB-1" in res.json()["detail"]

    def down(path):
        raise virus_scan.ScannerUnavailable("connection refused")

    monkeypatch.setattr(virus_scan, "scan", down)
    assert upload(client, h).status_code == 503
    assert client.get("/api/proposals/mine", headers=h).json()["versions"] == []
    assert list((tmp_path / "proposals").iterdir()) == []  # neither file was kept
