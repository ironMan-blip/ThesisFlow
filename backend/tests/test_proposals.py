import re
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.milestone import MilestoneTemplate, Phase
from app.models.user import Role
from app.schemas.proposal import MAX_ABSTRACT_CHARS
from app.services import proposal_service
from tests.helpers import PDF, REASON, auth, me, run_deletions_due, student, supervised_student, upload

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
    # SRS F11: every upload is a new version and old ones are kept.
    h = student(client, db, "s@x.com")
    v = upload(client, h).json()["versions"][0]
    assert client.delete(f"/api/proposals/versions/{v['id']}", headers=h).status_code == 404
    assert client.get(f"/api/proposals/versions/{v['id']}/file", headers=h).status_code == 200
    assert "can_delete" not in v


def test_pdf_needs_its_eof_trailer(client, db):
    h = student(client, db, "s@x.com")
    assert upload(client, h, content=b"%PDF-1.4\nnot really a pdf").status_code == 422
    assert upload(client, h, content=PDF + b"\n" * 100).status_code == 201  # trailing bytes after %%EOF are fine
    assert upload(client, h, content=PDF + b"x" * 2048).status_code == 422  # %%EOF not near the end


def _ask(client, h, v, body=REASON):
    return client.post(f"/api/proposals/versions/{v['id']}/delete-request", headers=h, json=body)


def _decide(client, sup, v, approve=True):
    url = f"/api/proposals/delete-requests/{v['id']}"
    return (client.post(url + "/approve", headers=sup) if approve else client.delete(url, headers=sup)).status_code


def test_a_version_delete_needs_a_reason_supervisor_approval_and_7_days(client, db, tmp_path):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    h, sup = supervised_student(client, db, "s@x.com")
    other = student(client, db, "o@x.com")
    for t in ("a", "b", "c"):
        upload(client, h, content=PDF + t.encode(), title=t)
    c, b, a = client.get("/api/proposals/mine", headers=h).json()["versions"]
    assert a["can_request_delete"] and not a["delete_pending"]

    assert _ask(client, other, a).status_code == 404  # not their version
    assert _ask(client, h, a, body={"reason": "oops"}).status_code == 422  # a reason, not a word
    row = _ask(client, h, a).json()["versions"][-1]
    assert (row["title"], row["delete_pending"], row["can_request_delete"], row["delete_executes_at"]) == ("a", True, False, None)
    assert _ask(client, h, a).status_code == 409  # already requested
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 1}  # waits for the supervisor
    [t] = client.get("/api/theses", headers=sup).json()
    assert t["is_supervisor"] and [(v["title"], v["delete_pending"], v["delete_reason"]) for v in t["versions"]][-1] == ("a", True, REASON["reason"])
    assert run_deletions_due(db) == (0, 0)  # 7 days alone do nothing without approval

    assert _decide(client, h, a) == 403  # students can't decide
    assert _decide(client, coord, a) == 403  # nor the coordinator: it's the supervisor's call
    assert _decide(client, auth(client, db, "f@x.com", Role.faculty), a) == 404  # another faculty member
    assert _decide(client, sup, a) == 204
    assert _decide(client, sup, a) == 404  # once
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 0}
    assert client.get("/api/proposals/mine", headers=h).json()["versions"][-1]["delete_executes_at"] is not None
    assert proposal_service.run_due_deletions(db) == 0  # approved, but the 7 days aren't over

    assert run_deletions_due(db) == (0, 1)
    versions = client.get("/api/proposals/mine", headers=h).json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("c", 2), ("b", 1)]
    assert len(list((tmp_path / "proposals").iterdir())) == 2  # the PDF is gone too
    assert client.get(f"/api/proposals/versions/{a['id']}/file", headers=h).status_code == 404
    versions = upload(client, h, content=PDF + b"d", title="d").json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("d", 3), ("c", 2), ("b", 1)]


def test_only_the_supervisor_cancels_a_version_delete(client, db):
    h, sup = supervised_student(client, db, "s@x.com")
    v = upload(client, h).json()["versions"][0]
    _ask(client, h, v)
    assert client.delete(f"/api/proposals/delete-requests/{v['id']}", headers=h).status_code == 403
    _decide(client, sup, v)
    # Uploading the same file again doesn't stop the delete either: it is stored as a new version.
    versions = upload(client, h).json()["versions"]
    assert [(x["version_no"], x["delete_pending"]) for x in versions] == [(2, False), (1, True)]

    assert _decide(client, sup, v, approve=False) == 204  # cancel an approved delete
    assert _decide(client, sup, v, approve=False) == 404
    assert client.get("/api/proposals/mine", headers=h).json()["versions"][1]["can_request_delete"] is True
    assert run_deletions_due(db) == (0, 0)
    assert len(client.get("/api/proposals/mine", headers=h).json()["versions"]) == 2

    # Approving after the phase closed is refused.
    _ask(client, h, v)
    p1 = db.get(MilestoneTemplate, Phase.P1)
    p1.due_at, p1.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 0
    db.flush()
    assert _decide(client, sup, v) == 409


def test_a_version_delete_lapses_when_the_phase_closes_first(client, db):
    h, sup = supervised_student(client, db, "s@x.com")
    v = upload(client, h).json()["versions"][0]
    _ask(client, h, v)
    _decide(client, sup, v)  # approved, then the phase closes
    p1 = db.get(MilestoneTemplate, Phase.P1)
    p1.due_at, p1.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 0  # closed: v is the final submission
    db.flush()
    mine = client.get("/api/proposals/mine", headers=h).json()["versions"][0]
    assert (mine["delete_pending"], mine["can_request_delete"], mine["delete_executes_at"]) == (False, False, None)
    assert _ask(client, h, v).status_code == 409
    assert run_deletions_due(db) == (0, 0)
    assert len(client.get("/api/proposals/mine", headers=h).json()["versions"]) == 1  # kept


def _schedule(client, headers, v, body=REASON):
    return client.post(f"/api/proposals/versions/{v['id']}/deletion", headers=headers, json=body)


def test_supervisor_deletes_a_version_directly_but_never_the_final_one(client, db, tmp_path):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    h, sup = supervised_student(client, db, "s@x.com")
    other_sup = auth(client, db, "f@x.com", Role.faculty)
    upload(client, h, content=PDF + b"a", title="a")
    b, a = upload(client, h, content=PDF + b"b", title="b").json()["versions"]

    assert _schedule(client, sup, b).status_code == 409  # b is the latest: the phase's final version
    assert _schedule(client, sup, a, body={}).status_code == 422  # a reason is required
    assert _schedule(client, other_sup, a).status_code == 404  # not their thesis
    assert _schedule(client, h, a).status_code == 403  # students ask instead
    assert _schedule(client, coord, a).status_code == 403  # only the supervisor deletes directly
    assert _schedule(client, sup, a).status_code == 204
    assert _schedule(client, sup, a).status_code == 409  # already scheduled

    # The student is told: badge, reason, date, and their supervisor's contact. They can't cancel.
    assert client.get("/api/auth/me/counts", headers=h).json() == {"proposal": 1}
    res = client.get("/api/proposals/mine", headers=h).json()
    row = res["versions"][1]
    assert (row["delete_pending"], row["delete_by_staff"], row["delete_reason"]) == (True, True, REASON["reason"])
    assert row["delete_executes_at"] is not None and row["can_request_delete"] is False
    assert res["supervisor_contact"] == me(client, sup)["email"]
    assert client.delete(f"/api/proposals/delete-requests/{a['id']}", headers=h).status_code == 403
    assert _decide(client, sup, a) == 404  # approved already
    theses = client.get("/api/theses", headers=sup).json()
    assert [(v["title"], v["delete_pending"], v["can_schedule_delete"]) for v in theses[0]["versions"]] == [("b", False, False), ("a", True, False)]

    assert run_deletions_due(db) == (0, 1)
    versions = client.get("/api/proposals/mine", headers=h).json()["versions"]
    assert [(v["title"], v["version_no"]) for v in versions] == [("b", 1)]
    assert len(list((tmp_path / "proposals").iterdir())) == 1
    assert client.get("/api/auth/me/counts", headers=h).json() == {}


def test_co_supervisor_cannot_delete_and_supervisor_cancels(client, db):
    h, sup = supervised_student(client, db, "s@x.com")
    co = auth(client, db, "co@x.com", Role.faculty)
    tid = client.get("/api/theses/mine", headers=h).json()["thesis"]["id"]
    client.post("/api/theses/mine/co-supervisor", headers=h, json={"co_supervisor_id": me(client, co)["id"]})
    for f in (co, sup):
        assert client.post(f"/api/theses/requests/{tid}/accept", headers=f).status_code == 204
    upload(client, h, content=PDF + b"a", title="a")
    b, a = upload(client, h, content=PDF + b"b", title="b").json()["versions"]
    assert _schedule(client, co, a).status_code == 403  # co-supervisor sees it but can't delete
    [t] = client.get("/api/theses", headers=co).json()
    assert t["is_supervisor"] is False and [v["can_schedule_delete"] for v in t["versions"]] == [False, False]
    assert _schedule(client, sup, a).status_code == 204
    assert _decide(client, co, a, approve=False) == 404  # nor cancel it
    assert _decide(client, sup, a, approve=False) == 204
    row = client.get("/api/proposals/mine", headers=h).json()["versions"][1]
    assert (row["delete_pending"], row["delete_rejected"]) == (False, False)  # a cancel isn't a rejection of the student
    assert run_deletions_due(db) == (0, 0)
    assert len(client.get("/api/proposals/mine", headers=h).json()["versions"]) == 2


def test_student_sees_a_rejected_request(client, db):
    h, sup = supervised_student(client, db, "s@x.com")
    v = upload(client, h).json()["versions"][0]
    _ask(client, h, v)
    assert _decide(client, sup, v, approve=False) == 204
    row = client.get("/api/proposals/mine", headers=h).json()["versions"][0]
    assert (row["delete_rejected"], row["can_request_delete"]) == (True, True)
    row = _ask(client, h, v).json()["versions"][0]  # asking again clears the old answer
    assert (row["delete_rejected"], row["delete_pending"]) == (False, True)


def test_uploads_per_phase_are_capped(client, db, monkeypatch):
    monkeypatch.setattr(proposal_service, "MAX_VERSIONS_PER_PHASE", 2)
    h = student(client, db, "cap@b.com")
    assert upload(client, h, title="one").status_code == 201
    assert upload(client, h, title="two").status_code == 201
    r = upload(client, h, title="three")
    assert r.status_code == 409 and "2 versions" in r.json()["detail"]
    # Re-sending a stored version adds nothing, so it still works at the cap.
    assert upload(client, h, title="one").status_code == 201
