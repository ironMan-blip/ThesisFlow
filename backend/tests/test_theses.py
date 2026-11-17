import itertools
import re
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, event

from app.models.milestone import GroupMilestone, MilestoneTemplate, Phase
from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role, User
from tests.conftest import engine
from tests.helpers import PDF, REASON, ask_supervisor, auth, close_registration, form_group, me, run_deletions_due, student, supervised_student, upload

pytestmark = pytest.mark.usefixtures("timelines")


def mine(client, h):
    return client.get("/api/theses/mine", headers=h).json()


def ask(client, db, h, supervisor):
    return ask_supervisor(client, db, h, supervisor)


def add_co(client, h, co):
    return client.post("/api/theses/mine/co-supervisor", headers=h, json={"co_supervisor_id": me(client, co)["id"]})


def answer(client, faculty, tid, yes=True):
    return client.post(f"/api/theses/requests/{tid}/{'accept' if yes else 'decline'}", headers=faculty).status_code


def user_of(client, db, h) -> User:
    return db.get(User, me(client, h)["id"])


def started_yesterday(client, db, h):
    # Backdate the phase start so a deadline that just passed counts as missed.
    user_of(client, db, h).thesis.phase_started_at -= timedelta(days=1)
    db.flush()


def close(db, phase):
    m = db.get(MilestoneTemplate, phase)
    m.due_at, m.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 0
    db.flush()


def reopen(db):
    # A new semester's deadlines.
    due = datetime.now(timezone.utc) + timedelta(days=30)
    db.add_all(MilestoneTemplate(phase=p, due_at=due, grace_days=0, penalty_per_day=0) for p in Phase)
    db.flush()


def close_all_and_roll(client, db, coord):
    for p in Phase:
        close(db, p)
    res = client.post("/api/milestones/next-semester", headers=coord)
    assert res.status_code == 200, res.json()
    return res.json()


def test_group_forms_when_the_supervisor_accepts(client, db):
    s = auth(client, db, "s@x.com")
    sup = auth(client, db, "sup@x.com", Role.faculty)
    coord = auth(client, db, "c@x.com", Role.coordinator)
    other_student = auth(client, db, "o@x.com")

    assert ask(client, db, s, other_student).status_code == 422  # supervisor must be faculty
    res = ask(client, db, s, sup)
    assert res.status_code == 201
    t = res.json()["thesis"]
    assert (t["status"], t["code"], t["co_supervisor"]) == ("pending", None, None)
    flags = mine(client, s)
    assert (flags["can_cancel"], flags["show_p1_registration"], flags["can_add_co_supervisor"]) == (True, False, False)
    assert add_co(client, s, auth(client, db, "co@x.com", Role.faculty)).status_code == 409  # only after forming
    assert ask(client, db, s, sup).status_code == 409  # one group at a time
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 1}
    assert answer(client, other_student, t["id"]) == 403

    assert answer(client, sup, t["id"]) == 204
    flags = mine(client, s)
    t = flags["thesis"]
    assert (t["status"], t["code"]) == ("formed", None)  # active, with a thesis ID, at P1 registration
    assert (flags["can_cancel"], flags["show_p1_registration"], flags["can_add_co_supervisor"]) == (False, True, True)
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 0}
    assert [x["id"] for x in client.get("/api/theses", headers=sup).json()] == [t["id"]]
    assert client.get("/api/theses", headers=s).status_code == 403
    assert client.get("/api/theses", headers=coord).status_code == 403  # the coordinator never sees theses


def test_co_supervisor_joins_a_formed_group_once_both_accept(client, db):
    s = auth(client, db, "s@x.com")
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    form_group(client, db, s, sup)
    assert upload(client, s).status_code == 409  # formed, not registered: no uploads yet
    assert client.post("/api/theses/mine/register", headers=s).status_code == 200
    t = mine(client, s)["thesis"]
    assert t["status"] == "active" and re.fullmatch(r"T\d{8}", t["code"])
    tid = mine(client, s)["thesis"]["id"]
    vid = upload(client, s).json()["versions"][0]["id"]
    file = lambda h: client.get(f"/api/proposals/versions/{vid}/file", headers=h).status_code

    choices = [p["id"] for p in mine(client, s)["faculty_choices"]]
    assert me(client, co)["id"] in choices and me(client, sup)["id"] not in choices
    assert add_co(client, s, sup).status_code == 422  # someone else than the supervisor
    state = add_co(client, s, co).json()
    assert (state["faculty_choices"], state["thesis"]["co_supervisor_joined"]) == ([], False)
    assert (state["can_add_co_supervisor"], state["can_cancel_co_supervisor"]) == (False, True)
    assert add_co(client, s, co).status_code == 409  # one at a time
    assert [r["slot"] for r in client.get("/api/theses/requests", headers=co).json()] == ["co_supervisor"]
    assert [r["slot"] for r in client.get("/api/theses/requests", headers=sup).json()] == ["co_supervisor_approval"]

    assert answer(client, co, tid) == 204
    t = mine(client, s)["thesis"]
    assert (t["co_supervisor_accepted"], t["co_supervisor_approved"]) == (True, False)
    assert file(co) == 404 and client.get("/api/theses", headers=co).json() == []  # not in until the supervisor agrees
    assert answer(client, sup, tid) == 204
    t = mine(client, s)["thesis"]
    assert (t["status"], t["co_supervisor_accepted"], t["co_supervisor_approved"], t["co_supervisor_joined"]) == ("active", True, True, True)
    assert file(co) == 200 and [x["id"] for x in client.get("/api/theses", headers=co).json()] == [tid]
    assert mine(client, s)["can_cancel_co_supervisor"] is False
    assert client.delete("/api/theses/mine/co-supervisor", headers=s).status_code == 409  # joined: stays


def test_either_declining_the_co_supervisor_keeps_the_group(client, db):
    s = auth(client, db, "s@x.com")
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    form_group(client, db, s, sup)
    tid = mine(client, s)["thesis"]["id"]

    add_co(client, s, co)
    assert answer(client, sup, tid) == 204
    assert answer(client, co, tid, yes=False) == 204
    state = mine(client, s)
    assert (state["thesis"]["status"], state["thesis"]["co_supervisor"], state["can_add_co_supervisor"]) == ("formed", None, True)

    add_co(client, s, co)
    assert answer(client, co, tid) == 204
    assert answer(client, sup, tid, yes=False) == 204
    assert mine(client, s)["thesis"]["co_supervisor"] is None
    assert client.get("/api/theses/requests", headers=co).json() == []

    add_co(client, s, co)
    assert client.delete("/api/theses/mine/co-supervisor", headers=s).json()["thesis"]["co_supervisor"] is None
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 0}


def test_a_stale_answer_never_approves_a_swapped_co_supervisor(client, db):
    s = auth(client, db, "s@x.com")
    sup = auth(client, db, "sup@x.com", Role.faculty)
    x, y = auth(client, db, "x@x.com", Role.faculty), auth(client, db, "y@x.com", Role.faculty)
    form_group(client, db, s, sup)
    tid = mine(client, s)["thesis"]["id"]
    add_co(client, s, x)
    seen = client.get("/api/theses/requests", headers=sup).json()[0]["co_supervisor"]["id"]  # supervisor's page shows x

    client.delete("/api/theses/mine/co-supervisor", headers=s)
    add_co(client, s, y)  # swapped before the supervisor clicks
    res = client.post(f"/api/theses/requests/{tid}/accept", headers=sup, params={"co_supervisor_id": seen})
    assert res.status_code == 409
    assert mine(client, s)["thesis"]["co_supervisor_approved"] is False


def test_declines_and_cancel(client, db):
    s = auth(client, db, "s@x.com")
    sup = auth(client, db, "sup@x.com", Role.faculty)
    tid = ask(client, db, s, sup).json()["thesis"]["id"]
    assert answer(client, sup, tid, yes=False) == 204
    assert mine(client, s)["thesis"] is None and mine(client, s)["can_form_group"] is True

    ask(client, db, s, sup)
    assert client.delete("/api/theses/mine", headers=s).json()["thesis"] is None
    form_group(client, db, s, sup)
    assert client.delete("/api/theses/mine", headers=s).status_code == 409  # an active group can't be cancelled


def test_missed_deadline_freezes_until_restart_at_p1(client, db):
    s, sup = supervised_student(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    old_thesis = mine(client, s)["thesis"]
    upload(client, s)
    # That upload was from an earlier phase, so it isn't a deliverable for this one.
    db.execute(delete(GroupMilestone))
    started_yesterday(client, db, s)
    close(db, Phase.P1)

    state = mine(client, s)
    assert state["frozen_reason"] == "Your group missed the P1 deadline" and state["can_form_group"] is False
    res = upload(client, s)
    assert res.status_code == 409 and "frozen" in res.json()["detail"]

    # Extending the deadline lifts the freeze before the semester ends.
    db.get(MilestoneTemplate, Phase.P1).grace_days = 2
    db.flush()
    assert mine(client, s)["frozen_reason"] is None
    close(db, Phase.P1)

    # Missed the extended deadline too: they can ask right away, mid-semester.
    assert client.post("/api/auth/me/restart-request", headers=coord).status_code == 409
    r = client.post("/api/auth/me/restart-request", headers=s)
    assert r.status_code == 200 and r.json()["restart_pending"] is True
    assert client.post("/api/auth/me/restart-request", headers=s).status_code == 409
    # No going back once asked: extending the deadline again doesn't reopen this thesis.
    db.get(MilestoneTemplate, Phase.P1).grace_days = 2
    db.flush()
    assert mine(client, s)["frozen_reason"] == "You asked to restart at P1"
    assert upload(client, s).status_code == 409
    close(db, Phase.P1)
    assert client.get("/api/auth/me/counts", headers=coord).json()["restart_requests"] == 1
    uid = client.get("/api/auth/restart-requests", headers=coord).json()[0]["id"]
    assert client.post(f"/api/auth/restart-requests/{uid}/approve", headers=coord).status_code == 200
    assert client.get("/api/auth/restart-requests", headers=coord).json() == []

    # Approved, but the fresh start waits for the next semester.
    state = mine(client, s)
    assert (state["restart_approved"], state["thesis"]["id"], state["frozen_reason"]) == (
        True, old_thesis["id"], "Your group missed the P1 deadline"
    )
    assert client.post("/api/auth/me/restart-request", headers=s).status_code == 409
    assert close_all_and_roll(client, db, coord)["restarted"] == 1

    state = mine(client, s)
    assert state["restart_approved"] is False
    # A fresh start leaves the old group too; the teammates (who didn't restart) keep the old thesis.
    assert (state["phase"], state["thesis"], state["frozen_reason"], state["form_group_block"]) == (
        None, None, None, "Create or join a group first"
    )
    form_group(client, db, s)
    new_thesis = mine(client, s)["thesis"]
    assert new_thesis["code"] != old_thesis["code"]  # a new thesis ID
    archived = {t["id"]: t for t in client.get("/api/theses", headers=sup).json()}
    assert archived[old_thesis["id"]]["status"] == "active"  # still the teammates' thesis
    assert len(archived[old_thesis["id"]]["versions"]) == 1  # nothing is lost


def test_extension_without_restart_request_lets_a_frozen_student_continue(client, db):
    s = student(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    started_yesterday(client, db, s)
    close(db, Phase.P1)
    assert mine(client, s)["frozen_reason"] == "Your group missed the P1 deadline"
    db.get(MilestoneTemplate, Phase.P1).grace_days = 2  # extended, and they never asked to restart
    db.flush()
    assert upload(client, s).status_code == 201
    assert close_all_and_roll(client, db, coord)["advanced"] == 1  # one thesis group
    assert me(client, s)["phase"] == "P2"


def test_restart_can_be_rejected(client, db):
    s = student(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    started_yesterday(client, db, s)
    close(db, Phase.P1)
    uid = client.post("/api/auth/me/restart-request", headers=s).json()["id"]
    r = client.delete(f"/api/auth/restart-requests/{uid}", headers=coord)
    assert r.status_code == 200 and r.json()["restart_pending"] is False
    assert mine(client, s)["frozen_reason"] == "Your group missed the P1 deadline"


def test_late_sign_up_waits_for_next_semester_instead_of_freezing(client, db):
    close(db, Phase.P1)
    s = auth(client, db, "late@x.com")  # phase starts after P1 closed
    assert mine(client, s)["frozen_reason"] is None
    coord = auth(client, db, "c@x.com", Role.coordinator)
    assert close_all_and_roll(client, db, coord)["frozen"] == 0
    assert me(client, s)["phase"] is None  # no thesis, so no phase yet


def test_groups_form_any_time_but_register_for_p1_only_in_the_first_week(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    sup = auth(client, db, "sup@x.com", Role.faculty)
    on_time, unregistered, late = (auth(client, db, f"{n}@x.com") for n in ("on_time", "unregistered", "late"))
    form_group(client, db, on_time, sup)
    state = mine(client, on_time)
    assert (state["registration_open"], state["can_register"], state["thesis"]["p1_registered"]) == (True, True, False)
    assert client.get("/api/proposals/mine", headers=on_time).json()["upload_block"] == (
        "Register your group for P1 on the Thesis page first"
    )
    state = client.post("/api/theses/mine/register", headers=on_time).json()
    assert (state["can_register"], state["thesis"]["p1_registered"]) == (False, True)
    assert client.post("/api/theses/mine/register", headers=on_time).status_code == 409  # once per semester
    assert upload(client, on_time).status_code == 201
    form_group(client, db, unregistered, sup)

    # After the first week, groups still form and get accepted, but can't register for P1.
    close_registration(db)
    assert mine(client, late)["form_group_block"] == "Create or join a group first"
    form_group(client, db, late, sup)
    assert mine(client, late)["can_register"] is False
    res = client.post("/api/theses/mine/register", headers=late)
    assert (res.status_code, res.json()["detail"]) == (409, "P1 registration is closed, register in the first week of next semester")
    assert "registration is closed" in client.get("/api/proposals/mine", headers=late).json()["upload_block"]

    # Not registered, so nothing was due: missing P1 doesn't freeze them.
    for h in (unregistered, late):
        started_yesterday(client, db, h)
    close(db, Phase.P1)
    assert [mine(client, h)["frozen_reason"] for h in (unregistered, late)] == [None, None]
    res = close_all_and_roll(client, db, coord)
    assert (res["advanced"], res["frozen"]) == (1, 0)  # on_time's group
    assert [me(client, h)["phase"] for h in (on_time, unregistered, late)] == ["P2", "P1", "P1"]

    # The new semester opens registration again.
    assert mine(client, late)["can_register"] is True
    assert client.post("/api/theses/mine/register", headers=late).status_code == 200


def test_rollover_moves_students_on_and_saves_freezes(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    done, missed = student(client, db, "done@x.com"), student(client, db, "missed@x.com")
    upload(client, done)
    started_yesterday(client, db, missed)

    assert client.post("/api/milestones/next-semester", headers=done).status_code == 403
    res = client.post("/api/milestones/next-semester", headers=coord)
    assert (res.status_code, res.json()["detail"]) == (409, "P1, P2, P3 is still open, wait until its grace period ends")

    # Counted per thesis group: done's moves on, missed's is frozen.
    assert close_all_and_roll(client, db, coord) == {
        "advanced": 1, "completed": 0, "deferred": 0, "cancelled": 0, "frozen": 1, "restarted": 0
    }
    assert me(client, done)["phase"] == "P2"
    assert [m["status"] for m in client.get("/api/milestones", headers=coord).json()["milestones"]] == ["not_set"] * 3
    # The freeze is saved, so it outlives the cleared deadlines.
    assert mine(client, missed)["frozen_reason"] == "Your group missed the P1 deadline"

    reopen(db)
    assert client.get("/api/proposals/mine", headers=done).json()["phase"] == "P2"
    assert upload(client, done, content=PDF + b"p2").json()["versions"][0]["phase"] == "P2"


def p3_student(client, db, email):
    """A P3 student and their supervisor, who decides deferrals (panel members later)."""
    s, sup = supervised_student(client, db, email)
    user_of(client, db, s).thesis.phase = Phase.P3
    db.flush()
    return s, sup


def test_p3_without_deferral_completes_the_thesis(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s, sup = p3_student(client, db, "s@x.com")
    tid = mine(client, s)["thesis"]["id"]
    assert client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": True}).status_code == 409  # nothing submitted
    upload(client, s)
    assert [t["can_defer"] for t in client.get("/api/theses", headers=sup).json()] == [True]
    assert client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True}).status_code == 403  # supervisor's call
    assert client.put(f"/api/theses/{tid}/defer", headers=auth(client, db, "f@x.com", Role.faculty), json={"defer": True}).status_code == 404
    assert client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": True}).json()["defer_pending"] is True
    assert client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": False}).json()["defer_pending"] is False

    assert close_all_and_roll(client, db, coord)["completed"] == 1
    state = mine(client, s)
    assert (state["phase"], state["thesis"]["status"]) == (None, "completed")
    reopen(db)
    assert client.get("/api/proposals/mine", headers=s).json()["upload_block"] == "Your thesis is complete"


def test_deferred_twice_cancels_the_thesis(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s, sup = p3_student(client, db, "s@x.com")
    tid = mine(client, s)["thesis"]["id"]
    upload(client, s)
    client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": True})
    assert close_all_and_roll(client, db, coord)["deferred"] == 1

    reopen(db)
    state = mine(client, s)
    assert (state["phase"], state["thesis"]["deferrals"], state["frozen_reason"]) == ("P3", 1, None)
    # Last semester's P3 upload doesn't count: it can't be deferred again until they resubmit.
    assert client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": True}).status_code == 409
    upload(client, s, content=PDF + b"again")
    client.put(f"/api/theses/{tid}/defer", headers=sup, json={"defer": True})
    assert close_all_and_roll(client, db, coord)["cancelled"] == 1
    # Cancelled: kept as an archive with its versions, and the group is free to ask a supervisor again.
    state = mine(client, s)
    assert (state["phase"], state["thesis"], state["frozen_reason"], state["can_form_group"]) == (None, None, None, True)
    archived = {t["id"]: t for t in client.get("/api/theses", headers=sup).json()}[tid]
    assert (archived["status"], len(archived["versions"])) == ("dropped", 2)


def test_faculty_who_accepted_a_group_are_kept_until_its_thesis_ends(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    s = auth(client, db, "s@x.com")
    schedule = lambda h: client.post(f"/api/auth/accounts/{me(client, h)['id']}/deletion", headers=coord, json=REASON).status_code
    unschedule = lambda h: client.delete(f"/api/auth/deletion-requests/{me(client, h)['id']}", headers=coord).status_code
    ask_delete = lambda h: client.post("/api/auth/me/deletion-request", headers=h, json=REASON).status_code

    ask(client, db, s, sup)
    assert schedule(sup) == 200  # a request they haven't accepted doesn't keep them
    assert unschedule(sup) == 200
    tid = mine(client, s)["thesis"]["id"]
    assert answer(client, sup, tid) == 204
    assert ask_delete(sup) == schedule(sup) == 409  # not by themselves, not by the coordinator

    add_co(client, s, co)
    assert schedule(co) == 200  # only invited
    assert unschedule(co) == 200
    assert answer(client, co, tid) == 204
    assert ask_delete(co) == schedule(co) == 409  # accepted, even before the supervisor agrees

    db.get(Thesis, tid).status = ThesisStatus.completed  # passed
    db.flush()
    assert ask_delete(co) == 200 and schedule(sup) == 200


def test_a_deletion_drops_requests_not_yet_accepted(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    f, sup2 = auth(client, db, "f@x.com", Role.faculty), auth(client, db, "sup2@x.com", Role.faculty)
    s1, s2 = auth(client, db, "s1@x.com"), auth(client, db, "s2@x.com")
    ask(client, db, s1, f)
    form_group(client, db, s2, sup2)
    add_co(client, s2, f)
    fid = me(client, f)["id"]
    assert client.post(f"/api/auth/accounts/{fid}/deletion", headers=coord, json=REASON).status_code == 200

    s3 = auth(client, db, "s3@x.com")
    assert fid not in [p["id"] for p in mine(client, s3)["faculty_choices"]]
    assert ask(client, db, s3, f).status_code == 422  # can't be picked while leaving
    assert answer(client, f, mine(client, s1)["thesis"]["id"]) == 409  # nor accept, which would keep the account
    assert run_deletions_due(db) == 1
    assert (mine(client, s1)["thesis"], mine(client, s1)["can_form_group"]) == (None, True)
    t2 = mine(client, s2)["thesis"]
    assert (t2["status"], t2["co_supervisor"], mine(client, s2)["can_add_co_supervisor"]) == ("formed", None, True)


def test_a_frozen_group_takes_no_new_co_supervisor(client, db):
    s, sup = supervised_student(client, db, "s@x.com")
    co = auth(client, db, "co@x.com", Role.faculty)
    tid = mine(client, s)["thesis"]["id"]
    add_co(client, s, co)
    started_yesterday(client, db, s)
    close(db, Phase.P1)
    assert mine(client, s)["frozen_reason"] == "Your group missed the P1 deadline"
    assert answer(client, co, tid) == 409
    assert answer(client, co, tid, yes=False) == 204  # declining still works


def test_faculty_pages_use_the_same_queries_for_any_number_of_theses(client, db, timelines):
    # The Theses page and the badge poll once ran several queries per thesis.
    sup = auth(client, db, "many@x.com", Role.faculty)
    queries = [0]
    event.listen(engine, "before_cursor_execute", count := lambda *a: queries.__setitem__(0, queries[0] + 1))

    def add_students(n):
        for _ in range(n):
            h = auth(client, db, f"s{next(_ids)}@x.com")
            form_group(client, db, h, sup)
            assert client.post("/api/theses/mine/register", headers=h).status_code == 200
            upload(client, h, content=PDF + b"a")
            upload(client, h, content=PDF + b"b")

    def cost():
        out = []
        for path in ("/api/theses", "/api/auth/me/counts"):
            queries[0] = 0
            assert client.get(path, headers=sup).status_code == 200
            out.append(queries[0])
        return out

    try:
        add_students(2)
        few = cost()
        add_students(4)
        assert cost() == few
    finally:
        event.remove(engine, "before_cursor_execute", count)


_ids = itertools.count()
