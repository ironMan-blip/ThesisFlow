import io
import re
from datetime import datetime, timedelta, timezone

import pytest
from pypdf import PdfReader
from pypdf.annotations import Link
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from sqlalchemy import select, update

from app import virus_scan
from app.config import settings
from app.models.milestone import MilestoneTemplate, Phase
from app.models.proposal import ProposalVersion
from app.models.user import Role, User
from app.schemas.proposal import MAX_ABSTRACT_CHARS
from app.services import proposal_service
from app.services.progress_service import current_semester_id
from tests.helpers import ask_supervisor, PDF, REASON, make_pdf, auth, me, student, supervised_student, upload


def _tagged(tag: str) -> bytes:
    # Distinct real PDFs: stored files are rewritten, so bytes appended after %%EOF don't survive.
    return make_pdf(lambda w: w.add_metadata({"/Title": tag}))


def _tag(content: bytes) -> str | None:
    return (PdfReader(io.BytesIO(content)).metadata or {}).get("/Title")

pytestmark = pytest.mark.usefixtures("timelines")


def test_each_upload_is_a_new_version_and_old_ones_stay(client, db):
    h = student(client, db, "s@x.com")
    empty = client.get("/api/proposals/mine", headers=h).json()
    assert (empty["versions"], empty["phase"], empty["upload_block"]) == ([], "P1", None)
    assert re.fullmatch(r"T\d{8}", empty["thesis_code"])

    assert upload(client, h).status_code == 201
    res = upload(client, h, content=_tagged("v2"), name="p2.pdf")
    assert res.status_code == 201
    versions = res.json()["versions"]
    assert [v["version_no"] for v in versions] == [2, 1]
    assert [v["original_filename"] for v in versions] == ["p2.pdf", "p.pdf"]
    assert [v["is_latest"] for v in versions] == [True, False]
    assert versions[0]["phase"] == "P1"
    assert versions[0]["size_label"].endswith(" KB")
    assert versions[0]["download_path"] == f"/proposals/versions/{versions[0]['id']}/file"

    old = client.get(f"/api/proposals/versions/{versions[1]['id']}/file", headers=h)
    assert old.status_code == 200
    assert _tag(old.content) is None  # version 1, not the tagged version 2
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
    ask_supervisor(client, db, h, sup)
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


def test_resubmitting_identical_upload_is_a_new_version(client, db, tmp_path):
    h = student(client, db, "s@x.com")
    for t in ("a", "b"):
        upload(client, h, content=_tagged(t), name=f"{t}.pdf")
    a = client.get("/api/proposals/mine", headers=h).json()["versions"][1]

    res = upload(client, h, content=_tagged("a"), name="a.pdf")
    assert res.status_code == 201
    versions = res.json()["versions"]
    # Every upload is kept as its own version, with its own upload time; the older ones are untouched.
    assert [(v["original_filename"], v["version_no"]) for v in versions] == [("a.pdf", 3), ("b.pdf", 2), ("a.pdf", 1)]
    assert versions[0]["is_latest"] and versions[0]["id"] != a["id"]
    assert (versions[2]["id"], versions[2]["created_at"]) == (a["id"], a["created_at"])
    assert len(list((tmp_path / "proposals").iterdir())) == 3
    assert _tag(client.get(f"/api/proposals/versions/{versions[0]['id']}/file", headers=h).content) == "a"


def _upload_as(client, h, title, abstract="About it", content=PDF):
    return client.post(
        "/api/proposals/mine/versions", headers=h, data={"title": title, "abstract": abstract},
        files={"file": ("p.pdf", content, "application/pdf")},
    )


def test_the_first_upload_fixes_the_title_and_abstract(client, db):
    h = student(client, db, "s@x.com")
    assert _upload_as(client, h, "  a  ").status_code == 201  # stored stripped
    mine = client.get("/api/proposals/mine", headers=h).json()
    assert (mine["title"], mine["abstract"]) == ("a", "About it")

    r = _upload_as(client, h, "a renamed", content=PDF + b"2")
    assert r.status_code == 422 and r.json()["detail"].startswith("Wrong title:")
    r = _upload_as(client, h, "a", "New abstract", content=PDF + b"2")
    assert r.status_code == 422 and r.json()["detail"].startswith("Wrong abstract:")
    r = _upload_as(client, h, "b", "New abstract", content=PDF + b"2")
    assert r.status_code == 422 and r.json()["detail"].startswith("Wrong title and abstract:")
    assert len(_upload_as(client, h, "a", content=PDF + b"2").json()["versions"]) == 2


def _ask_title(client, h, title, abstract="New abstract"):
    return client.post("/api/proposals/mine/title-change", headers=h, json={"title": title, "abstract": abstract})


def test_one_title_change_needs_the_supervisors_ok_within_3_days(client, db):
    from app.models.thesis import TitleChange
    h, sup = supervised_student(client, db, "s@x.com")
    other = auth(client, db, "f@x.com", Role.faculty)
    r = _ask_title(client, h, "b")
    assert r.status_code == 409 and "first version" in r.json()["detail"]
    _upload_as(client, h, "a")
    assert client.get("/api/proposals/mine", headers=h).json()["can_request_title_change"] is True
    assert _ask_title(client, h, "a", "About it").status_code == 422  # nothing would change

    res = _ask_title(client, h, "b")
    assert res.status_code == 201
    body = res.json()
    change = body["title_change"]
    assert (change["title"], change["status"], body["can_request_title_change"], body["title"]) == ("b", "pending", False, "a")
    assert _ask_title(client, h, "c").status_code == 409  # one request at a time
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 1}
    assert client.get("/api/theses", headers=sup).json()[0]["title_change_request"]["id"] == change["id"]

    url = f"/api/proposals/title-changes/{change['id']}"
    assert client.post(f"{url}/approve", headers=h).status_code == 403
    assert client.post(f"{url}/approve", headers=other).status_code == 404
    assert client.delete(url, headers=sup).status_code == 204  # rejected: the change isn't used up
    body = client.get("/api/proposals/mine", headers=h).json()
    assert (body["title_change"]["status"], body["can_request_title_change"]) == ("rejected", True)
    assert client.delete(url, headers=sup).status_code == 409

    # Not accepted within 3 days: it lapses, and the group can ask again.
    change = _ask_title(client, h, "b").json()["title_change"]
    db.get(TitleChange, change["id"]).created_at -= timedelta(days=3)
    db.flush()
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 0}
    r = client.post(f"/api/proposals/title-changes/{change['id']}/approve", headers=sup)
    assert r.status_code == 409 and "expired" in r.json()["detail"]
    assert client.get("/api/proposals/mine", headers=h).json()["title_change"]["status"] == "expired"

    change = _ask_title(client, h, "b").json()["title_change"]
    assert client.post(f"/api/proposals/title-changes/{change['id']}/approve", headers=sup).status_code == 204
    body = client.get("/api/proposals/mine", headers=h).json()
    assert (body["title"], body["abstract"], body["can_request_title_change"]) == ("b", "New abstract", False)
    assert _upload_as(client, h, "a", content=PDF + b"2").status_code == 422  # the old title is gone
    versions = _upload_as(client, h, "b", "New abstract", content=PDF + b"2").json()["versions"]
    # Older versions keep the title they were uploaded with; the first one after the change is marked.
    assert [(v["title"], v["title_changed"], v["abstract_changed"]) for v in versions] == [("b", True, True), ("a", False, False)]


def test_a_dot_only_file_name_falls_back(client, db, timelines):
    h = student(client, db, "s@x.com")
    assert upload(client, h, name="..").json()["versions"][0]["original_filename"] == "proposal.pdf"


def test_a_title_change_cant_be_approved_once_the_thesis_isnt_active(client, db, timelines):
    from app.models.thesis import Thesis, ThesisStatus
    h, sup = supervised_student(client, db, "s@x.com")
    _upload_as(client, h, "a")
    change = _ask_title(client, h, "b").json()["title_change"]
    db.execute(update(Thesis).values(status=ThesisStatus.dropped))
    db.flush()
    url = f"/api/proposals/title-changes/{change['id']}"
    assert client.post(f"{url}/approve", headers=sup).status_code == 409
    assert client.delete(url, headers=sup).status_code == 204  # rejecting still works


def test_line_endings_dont_break_the_exact_title_match(client, db, timelines):
    # Form uploads arrive with CRLF, the JSON title change with LF: both are stored and compared as LF.
    h, sup = supervised_student(client, db, "s@x.com")
    assert _upload_as(client, h, "a", "one\r\ntwo").json()["abstract"] == "one\ntwo"
    change = _ask_title(client, h, "b", "three\nfour").json()["title_change"]
    assert client.post(f"/api/proposals/title-changes/{change['id']}/approve", headers=sup).status_code == 204
    assert _upload_as(client, h, "b", "three\r\nfour", content=PDF + b"2").status_code == 201
    assert client.get("/api/theses", headers=sup).json()[0]["versions"][0]["title_changed"] is True
    r = _ask_title(client, h, "c")
    assert r.status_code == 409 and "already used" in r.json()["detail"]


def test_upload_needs_the_phase_timeline(client, db):
    h = student(client, db, "s@x.com")
    db.delete(db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))))
    db.flush()
    mine = client.get("/api/proposals/mine", headers=h).json()
    assert mine["upload_block"] == "The P1 timeline is not set yet"
    res = upload(client, h)
    assert (res.status_code, res.json()["detail"]) == (409, "The P1 timeline is not set yet")


def test_grace_period_warns_and_then_uploads_close(client, db):
    h = student(client, db, "s@x.com")
    p1 = db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db)))
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
        # /S as an indirect reference: viewers resolve it, so the check must too.
        make_pdf(lambda w: w._root_object.__setitem__(NameObject("/OpenAction"), DictionaryObject(
            {NameObject("/S"): w._add_object(NameObject("/Launch")), NameObject("/F"): TextStringObject("calc.exe")}
        ))),
        make_pdf(lambda w: _open_action(w, {"/S": "/GoToR", "/F": "\\\\attacker\\share\\x.pdf"})),
        # Links that open local files, shares or OS protocol handlers instead of a web page.
        make_pdf(lambda w: _open_action(w, {"/S": "/URI", "/URI": "file:///C:/Windows/System32/calc.exe"})),
        make_pdf(lambda w: _open_action(w, {"/S": "/URI", "/URI": "\\\\attacker\\share"})),
        make_pdf(lambda w: _open_action(w, {"/S": "/URI", "/URI": "ms-msdt:/id PCWDiagnostic"})),
        # A web link that opens by itself (on open, on page view) tells the uploader when and where it was read.
        make_pdf(lambda w: _open_action(w, {"/S": "/URI", "/URI": "https://tracker.example/pixel"})),
        make_pdf(lambda w: _open_action(w, {"/S": "/GoTo", "/D": "/x", "/Next": "/x"})),
        make_pdf(lambda w: w.pages[0].__setitem__(NameObject("/AA"), DictionaryObject())),
        # Embedded media.
        make_pdf(lambda w: _open_action(w, {"/S": "/Sound"})),
        make_pdf(lambda w: _open_action(w, {"/S": "/Rendition"})),
        make_pdf(lambda w: w.add_annotation(0, DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Screen"),
            NameObject("/Rect"): ArrayObject(),
        }))),
        make_pdf(lambda w: w.add_attachment("run.exe", b"MZ")),
        make_pdf(lambda w: w.encrypt("secret")),
    ):
        res = upload(client, h, content=bad)
        assert res.status_code == 422, res.json()
    assert len(client.get("/api/proposals/mine", headers=h).json()["versions"]) == 1
    assert len(list((tmp_path / "proposals").iterdir())) == 1  # refused files are not kept


def test_web_links_are_kept(client, db):
    h = student(client, db, "links@x.com")
    for uri in ("https://example.com/paper", "mailto:a@b.com"):
        content = make_pdf(lambda w: w.add_annotation(0, Link(rect=(0, 0, 10, 10), url=uri)))  # opens only on click
        assert upload(client, h, content=content).status_code == 201
    # What LaTeX and Word write: open at a page, as a destination or a plain GoTo.
    for open_action in (
        lambda w: w._root_object.__setitem__(NameObject("/OpenAction"), ArrayObject([w.pages[0].indirect_reference, NameObject("/Fit")])),
        lambda w: w._root_object.__setitem__(NameObject("/OpenAction"), DictionaryObject({
            NameObject("/S"): NameObject("/GoTo"), NameObject("/D"): ArrayObject([w.pages[0].indirect_reference, NameObject("/Fit")]),
        })),
    ):
        assert upload(client, h, content=make_pdf(open_action)).status_code == 201


def test_stored_pdf_is_the_checked_rewrite(client, db, tmp_path):
    # An unreferenced object is skipped by the check but a repairing viewer could still find it: it must not be stored.
    hidden = b"99 0 obj\n<< /S /JavaScript /JS (app.alert(1)) >>\nendobj\n"
    h = student(client, db, "rewrite@x.com")
    header, rest = PDF.split(b"\n", 1)
    res = upload(client, h, content=header + b"\n" + hidden + rest)
    assert res.status_code == 201, res.json()
    (stored,) = (tmp_path / "proposals").iterdir()
    data = stored.read_bytes()
    assert b"app.alert" not in data and data.startswith(b"%PDF-")
    assert res.json()["versions"][0]["size_bytes"] == len(data)


def test_uploads_per_phase_are_capped(client, db, monkeypatch):
    monkeypatch.setattr(proposal_service, "MAX_VERSIONS_PER_PHASE", 2)
    h = student(client, db, "cap@b.com")
    assert upload(client, h, content=PDF + b"1").status_code == 201
    assert upload(client, h, content=PDF + b"2").status_code == 201
    r = upload(client, h, content=PDF + b"3")
    assert r.status_code == 409 and "2 versions" in r.json()["detail"]
    # Re-sending a stored file is a new version too, so the cap holds it back.
    assert upload(client, h, content=PDF + b"1").status_code == 409
    # Refused before the file is saved or scanned, so uploads at the cap cost the server nothing.
    monkeypatch.setattr(virus_scan, "scan", lambda path: pytest.fail("scanned an upload over the cap"))
    assert upload(client, h, content=PDF + b"4").status_code == 409


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


def test_recheck_rewrites_old_files_and_keeps_failures(client, db, tmp_path):
    # Files stored before uploads were rewritten get the same rewrite; a file that now fails is kept, only reported.
    h = student(client, db, "old@x.com")
    upload(client, h, content=_tagged("ok"))
    upload(client, h, content=_tagged("bad"))
    good, bad = sorted(db.scalars(select(ProposalVersion)), key=lambda v: v.version_no)
    hidden = b"99 0 obj\n<< /S /JavaScript /JS (app.alert(1)) >>\nendobj\n"
    header, rest = PDF.split(b"\n", 1)
    old = header + b"\n" + hidden + rest  # what an upload stored before the rewrite existed
    (tmp_path / "proposals" / good.stored_filename).write_bytes(old)
    linked = make_pdf(lambda w: _open_action(w, {"/S": "/Launch", "/F": "calc.exe"}))
    (tmp_path / "proposals" / bad.stored_filename).write_bytes(linked)

    rewritten, failed = proposal_service.recheck_stored_files(db)
    assert rewritten == 1 and [vid for vid, _ in failed] == [bad.id]
    data = (tmp_path / "proposals" / good.stored_filename).read_bytes()
    assert b"app.alert" not in data and db.get(ProposalVersion, good.id).size_bytes == len(data)
    assert (tmp_path / "proposals" / bad.stored_filename).read_bytes() == linked  # never deleted (SRS F11)


def test_a_frozen_group_cannot_change_its_title(client, db):
    h, sup = supervised_student(client, db, "s@x.com")
    assert upload(client, h).status_code == 201
    res = client.post("/api/proposals/mine/title-change", headers=h, json={"title": "New", "abstract": "New one"})
    assert res.status_code == 201
    change_id = res.json()["title_change"]["id"]
    thesis = db.get(User, me(client, h)["id"]).thesis
    thesis.frozen_at = datetime.now(timezone.utc)
    db.flush()
    assert client.post(f"/api/proposals/title-changes/{change_id}/approve", headers=sup).status_code == 409
    assert client.get("/api/proposals/mine", headers=h).json()["can_request_title_change"] is False
    assert client.delete(f"/api/proposals/title-changes/{change_id}", headers=sup).status_code == 204  # rejecting still works
    res = client.post("/api/proposals/mine/title-change", headers=h, json={"title": "New", "abstract": "New one"})
    assert (res.status_code, res.json()["detail"]) == (409, "Your group is frozen, so it can't change its title and abstract")
