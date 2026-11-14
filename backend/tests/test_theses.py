from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.models.milestone import Milestone, Phase
from app.models.proposal import ProposalVersion
from app.models.user import Role, User
from tests.helpers import PDF, auth, form_group, me, student, upload

pytestmark = pytest.mark.usefixtures("timelines")


def mine(client, h):
    return client.get("/api/theses/mine", headers=h).json()


def ask(client, h, supervisor, co=None):
    body = {"supervisor_id": me(client, supervisor)["id"], "co_supervisor_id": co and me(client, co)["id"]}
    return client.post("/api/theses/mine", headers=h, json=body)


def user_of(client, db, h) -> User:
    return db.get(User, me(client, h)["id"])


def started_yesterday(client, db, h):
    # Backdate the phase start so a deadline that just passed counts as missed.
    user_of(client, db, h).phase_started_at -= timedelta(days=1)
    db.flush()


def close(db, phase):
    m = db.get(Milestone, phase)
    m.due_at, m.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 0
    db.flush()


def reopen(db):
    # A new semester's deadlines.
    due = datetime.now(timezone.utc) + timedelta(days=30)
    db.add_all(Milestone(phase=p, due_at=due, grace_days=0, penalty_per_day=0) for p in Phase)
    db.flush()


def close_all_and_roll(client, db, coord):
    for p in Phase:
        close(db, p)
    res = client.post("/api/milestones/next-semester", headers=coord)
    assert res.status_code == 200, res.json()
    return res.json()


def test_group_needs_supervisor_acceptance_and_gets_a_thesis_id(client, db):
    s = auth(client, db, "s@x.com")
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    other_student = auth(client, db, "o@x.com")

    assert ask(client, s, other_student).status_code == 422  # supervisor must be faculty
    assert ask(client, s, sup, co=sup).status_code == 422  # co-supervisor must be someone else
    assert {f["email"] for f in client.get("/api/theses/faculty", headers=s).json()} == {"co@x.com", "sup@x.com"}

    res = ask(client, s, sup, co=co)
    assert res.status_code == 201
    t = res.json()["thesis"]
    assert (t["status"], t["code"], t["co_supervisor_accepted"]) == ("pending", None, False)
    assert ask(client, s, sup).status_code == 409  # one group at a time
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 1}
    assert [r["slot"] for r in client.get("/api/theses/requests", headers=co).json()] == ["co_supervisor"]
    assert client.post(f"/api/theses/requests/{t['id']}/accept", headers=other_student).status_code == 403

    assert client.post(f"/api/theses/requests/{t['id']}/accept", headers=sup).status_code == 204
    t = mine(client, s)["thesis"]
    assert (t["status"], t["code"]) == ("active", f"TH-{t['id']:04d}")
    assert client.get("/api/auth/me/counts", headers=sup).json() == {"theses": 0}
    assert client.get("/api/theses", headers=co).json() == []  # not accepted yet: not their thesis
    assert client.post(f"/api/theses/requests/{t['id']}/accept", headers=co).status_code == 204
    assert [x["id"] for x in client.get("/api/theses", headers=co).json()] == [t["id"]]
    assert client.get("/api/theses", headers=s).status_code == 403


def test_declines_and_cancel(client, db):
    s = auth(client, db, "s@x.com")
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    tid = ask(client, s, sup, co=co).json()["thesis"]["id"]

    assert client.post(f"/api/theses/requests/{tid}/decline", headers=co).status_code == 204
    assert mine(client, s)["thesis"]["co_supervisor"] is None  # optional, so the group stands
    assert client.post(f"/api/theses/requests/{tid}/decline", headers=sup).status_code == 204
    assert mine(client, s)["thesis"] is None and mine(client, s)["can_form_group"] is True

    ask(client, s, sup)
    assert client.delete("/api/theses/mine", headers=s).json()["thesis"] is None
    form_group(client, db, s, sup)
    assert client.delete("/api/theses/mine", headers=s).status_code == 409  # an active group can't be cancelled


def test_missed_deadline_freezes_until_restart_at_p1(client, db):
    s = student(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    old_thesis = mine(client, s)["thesis"]
    upload(client, s)
    # That upload was from an earlier phase, so it doesn't count for this one.
    db.execute(update(ProposalVersion).values(created_at=datetime.now(timezone.utc) - timedelta(days=2)))
    started_yesterday(client, db, s)
    close(db, Phase.P1)

    state = mine(client, s)
    assert state["frozen_reason"] == "You missed the P1 deadline" and state["can_form_group"] is False
    res = upload(client, s)
    assert res.status_code == 409 and "frozen" in res.json()["detail"]

    # Extending the deadline lifts the freeze before the semester ends.
    db.get(Milestone, Phase.P1).grace_days = 2
    db.flush()
    assert mine(client, s)["frozen_reason"] is None
    close(db, Phase.P1)

    # Missed the extended deadline too: they can ask right away, mid-semester.
    assert client.post("/api/auth/me/restart-request", headers=coord).status_code == 409
    r = client.post("/api/auth/me/restart-request", headers=s)
    assert r.status_code == 200 and r.json()["restart_pending"] is True
    assert client.post("/api/auth/me/restart-request", headers=s).status_code == 409
    # No going back once asked: extending the deadline again doesn't reopen this thesis.
    db.get(Milestone, Phase.P1).grace_days = 2
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
        True, old_thesis["id"], "You missed the P1 deadline"
    )
    assert client.post("/api/auth/me/restart-request", headers=s).status_code == 409
    assert close_all_and_roll(client, db, coord)["restarted"] == 1

    state = mine(client, s)
    assert state["restart_approved"] is False
    assert (state["phase"], state["thesis"], state["frozen_reason"], state["can_form_group"]) == ("P1", None, None, True)
    form_group(client, db, s)
    new_thesis = mine(client, s)["thesis"]
    assert new_thesis["code"] != old_thesis["code"]  # a new thesis ID
    archived = {t["id"]: t for t in client.get("/api/theses", headers=coord).json()}
    assert archived[old_thesis["id"]]["status"] == "dropped"
    assert len(archived[old_thesis["id"]]["versions"]) == 1  # nothing is lost


def test_extension_without_restart_request_lets_a_frozen_student_continue(client, db):
    s = student(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    started_yesterday(client, db, s)
    close(db, Phase.P1)
    assert mine(client, s)["frozen_reason"] == "You missed the P1 deadline"
    db.get(Milestone, Phase.P1).grace_days = 2  # extended, and they never asked to restart
    db.flush()
    assert upload(client, s).status_code == 201
    assert close_all_and_roll(client, db, coord)["advanced"] == 1
    assert me(client, s)["phase"] == "P2"


def test_restart_can_be_rejected(client, db):
    s = auth(client, db, "s@x.com")
    coord = auth(client, db, "c@x.com", Role.coordinator)
    started_yesterday(client, db, s)
    close(db, Phase.P1)
    uid = client.post("/api/auth/me/restart-request", headers=s).json()["id"]
    r = client.delete(f"/api/auth/restart-requests/{uid}", headers=coord)
    assert r.status_code == 200 and r.json()["restart_pending"] is False
    assert mine(client, s)["frozen_reason"] == "You missed the P1 deadline"


def test_late_sign_up_waits_for_next_semester_instead_of_freezing(client, db):
    close(db, Phase.P1)
    s = auth(client, db, "late@x.com")  # phase starts after P1 closed
    assert mine(client, s)["frozen_reason"] is None
    coord = auth(client, db, "c@x.com", Role.coordinator)
    assert close_all_and_roll(client, db, coord)["frozen"] == 0
    assert me(client, s)["phase"] == "P1"


def test_rollover_moves_students_on_and_saves_freezes(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    done, missed = student(client, db, "done@x.com"), student(client, db, "missed@x.com")
    upload(client, done)
    started_yesterday(client, db, missed)

    assert client.post("/api/milestones/next-semester", headers=done).status_code == 403
    res = client.post("/api/milestones/next-semester", headers=coord)
    assert (res.status_code, res.json()["detail"]) == (409, "P1, P2, P3 is still open, wait until its grace period ends")

    assert close_all_and_roll(client, db, coord) == {"advanced": 1, "completed": 0, "deferred": 0, "frozen": 1, "restarted": 0}
    assert me(client, done)["phase"] == "P2"
    assert [m["status"] for m in client.get("/api/milestones", headers=coord).json()["milestones"]] == ["not_set"] * 3
    # The freeze is saved, so it outlives the cleared deadlines.
    assert mine(client, missed)["frozen_reason"] == "You missed the P1 deadline"

    reopen(db)
    assert client.get("/api/proposals/mine", headers=done).json()["phase"] == "P2"
    assert upload(client, done, content=PDF + b"p2").json()["versions"][0]["phase"] == "P2"


def p3_student(client, db, email):
    s = student(client, db, email)
    user_of(client, db, s).phase = Phase.P3
    db.flush()
    return s


def test_p3_without_deferral_completes_the_thesis(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s = p3_student(client, db, "s@x.com")
    tid = mine(client, s)["thesis"]["id"]
    assert client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True}).status_code == 409  # nothing submitted
    upload(client, s)
    assert [t["can_defer"] for t in client.get("/api/theses", headers=coord).json()] == [True]
    assert client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True}).json()["defer_pending"] is True
    assert client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": False}).json()["defer_pending"] is False

    assert close_all_and_roll(client, db, coord)["completed"] == 1
    state = mine(client, s)
    assert (state["phase"], state["thesis"]["status"]) == (None, "completed")
    reopen(db)
    assert client.get("/api/proposals/mine", headers=s).json()["upload_block"] == "Your thesis is complete"


def test_deferred_twice_freezes(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s = p3_student(client, db, "s@x.com")
    tid = mine(client, s)["thesis"]["id"]
    upload(client, s)
    client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True})
    assert close_all_and_roll(client, db, coord)["deferred"] == 1

    reopen(db)
    state = mine(client, s)
    assert (state["phase"], state["thesis"]["deferrals"], state["frozen_reason"]) == ("P3", 1, None)
    # Last semester's P3 upload doesn't count: it can't be deferred again until they resubmit.
    assert client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True}).status_code == 409
    old = client.get("/api/proposals/mine", headers=s).json()["versions"][0]
    assert old["can_delete"] is False
    upload(client, s, content=PDF + b"again")
    client.put(f"/api/theses/{tid}/defer", headers=coord, json={"defer": True})
    assert close_all_and_roll(client, db, coord)["frozen"] == 1
    assert mine(client, s)["frozen_reason"] == "Your thesis was deferred twice"

    uid = me(client, s)["id"]
    client.post("/api/auth/me/restart-request", headers=s)
    client.post(f"/api/auth/restart-requests/{uid}/approve", headers=coord)
    reopen(db)
    assert close_all_and_roll(client, db, coord)["restarted"] == 1
    state = mine(client, s)
    assert (state["phase"], state["thesis"], state["frozen_reason"]) == ("P1", None, None)
