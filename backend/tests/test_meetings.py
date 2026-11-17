

from datetime import datetime, timedelta, timezone

from app.models.thesis import Thesis, ThesisStatus
from app.models.user import Role
from tests.helpers import auth, me


def ago(**delta):
    return (datetime.now(timezone.utc) - timedelta(**delta)).isoformat()


def body(**over):
    return {"held_at": ago(days=1), "notes": "Discussed the method.", "student_attended": True, "tasks": [], **over}


def group(client, db, co=False, co_joins=True, register=True):
    """A thesis group, registered for P1 unless told not to. Returns (student, supervisor, co-supervisor or None, thesis id)."""
    s = auth(client, db, "s@x.com")
    sup = auth(client, db, "sup@x.com", Role.faculty)
    res = client.post("/api/theses/mine", headers=s, json={"supervisor_id": me(client, sup)["id"]})
    assert res.status_code == 201, res.json()
    tid = res.json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=sup).status_code == 204
    co_h = auth(client, db, "co@x.com", Role.faculty) if co else None
    if co:
        assert client.post("/api/theses/mine/co-supervisor", headers=s, json={"co_supervisor_id": me(client, co_h)["id"]}).status_code == 200
        assert client.post(f"/api/theses/requests/{tid}/accept", headers=co_h).status_code == 204
        if co_joins:
            assert client.post(f"/api/theses/requests/{tid}/accept", headers=sup).status_code == 204
    if register:
        assert client.post("/api/theses/mine/register", headers=s).status_code == 200
    return s, sup, co_h, tid


def log(client, h, tid, **over):
    return client.post(f"/api/meetings/thesis/{tid}", headers=h, json=body(**over))


def test_supervisor_logs_a_meeting_and_the_right_people_see_it(client, db):
    s, sup, _, tid = group(client, db)
    res = log(client, sup, tid, tasks=[{"description": "Draft chapter 2", "due_at": ago(days=-7)}])
    assert res.status_code == 201, res.json()
    m = res.json()
    assert (m["supervisor_attended"], m["student_attended"], m["co_supervisor_attended"]) == (True, True, False)
    assert m["recorded_by"]["id"] == me(client, sup)["id"]
    assert [(t["description"], t["done"]) for t in m["tasks"]] == [("Draft chapter 2", False)]

    mine = client.get("/api/meetings/mine", headers=s).json()
    assert [x["id"] for x in mine["meetings"]] == [m["id"]]
    assert (mine["can_edit"], mine["log_block"]) == (False, None)

    listing = client.get(f"/api/meetings/thesis/{tid}", headers=sup).json()
    assert [x["id"] for x in listing["meetings"]] == [m["id"]] and listing["can_edit"] is True

    coord = auth(client, db, "c@x.com", Role.coordinator)
    assert client.get(f"/api/meetings/thesis/{tid}", headers=coord).status_code == 404  # coordinators never see theses
    assert log(client, coord, tid).status_code == 403
    assert log(client, s, tid).status_code == 403

    outsider = auth(client, db, "other@x.com", Role.faculty)
    assert client.get(f"/api/meetings/thesis/{tid}", headers=outsider).status_code == 404
    assert log(client, outsider, tid).status_code == 404
    other_student = auth(client, db, "o@x.com")
    assert client.get(f"/api/meetings/thesis/{tid}", headers=other_student).status_code == 404
    assert client.get("/api/meetings/mine", headers=other_student).json()["thesis"] is None


def test_newest_meeting_comes_first(client, db):
    _, sup, _, tid = group(client, db)
    old = log(client, sup, tid, held_at=ago(days=5)).json()["id"]
    new = log(client, sup, tid, held_at=ago(days=1)).json()["id"]
    listing = client.get(f"/api/meetings/thesis/{tid}", headers=sup).json()
    assert [m["id"] for m in listing["meetings"]] == [new, old]


def test_validation(client, db):
    s, sup, _, tid = group(client, db)
    assert log(client, sup, tid, held_at=ago(minutes=-5)).status_code == 422  # in the future
    assert log(client, sup, tid, held_at=ago(seconds=-30)).status_code == 201  # clock skew is tolerated
    assert log(client, sup, tid, held_at="2026-11-10T10:00:00").status_code == 422  # no time zone
    assert log(client, sup, tid, notes="   ").status_code == 422
    assert log(client, sup, tid, notes="x" * 5001).status_code == 422
    assert log(client, sup, tid, supervisor_attended=False, student_attended=False).status_code == 422
    assert log(client, sup, tid, co_supervisor_attended=True).status_code == 422  # no co-supervisor
    assert log(client, sup, tid, tasks=[{"description": " "}]).status_code == 422
    assert log(client, sup, tid, tasks=[{"description": "x"}] * 21).status_code == 422
    early = {"description": "x", "due_at": ago(days=3)}
    assert log(client, sup, tid, held_at=ago(days=2), tasks=[early]).status_code == 422  # due before the meeting
    # A student who did not come is a valid record.
    assert log(client, sup, tid, held_at=ago(days=9), student_attended=False).status_code == 201


def test_same_time_twice_is_refused(client, db):
    _, sup, _, tid = group(client, db)
    held = ago(days=1)
    assert log(client, sup, tid, held_at=held).status_code == 201
    assert log(client, sup, tid, held_at=held).status_code == 409  # a double click


def test_edit_keeps_task_state_and_delete_removes_everything(client, db):
    s, sup, _, tid = group(client, db)
    m = log(client, sup, tid, tasks=[{"description": "A"}, {"description": "B"}]).json()
    a, b = m["tasks"]

    done = client.put(f"/api/meetings/tasks/{a['id']}", headers=sup, json={"done": True})
    assert done.status_code == 200 and [t["done"] for t in done.json()["tasks"]] == [True, False]
    assert client.put(f"/api/meetings/tasks/{a['id']}", headers=s, json={"done": False}).status_code == 403

    edit = body(notes="Edited", tasks=[{"id": a["id"], "description": "A2"}, {"description": "C"}])
    res = client.put(f"/api/meetings/{m['id']}", headers=sup, json=edit)
    assert res.status_code == 200, res.json()
    out = res.json()
    assert out["notes"] == "Edited"
    assert [(t["description"], t["done"]) for t in out["tasks"]] == [("A2", True), ("C", False)]  # B is gone, A stays done

    bad = body(tasks=[{"id": b["id"], "description": "B"}])  # B no longer exists
    assert client.put(f"/api/meetings/{m['id']}", headers=sup, json=bad).status_code == 422
    twice = body(tasks=[{"id": a["id"], "description": "A"}, {"id": a["id"], "description": "A"}])
    assert client.put(f"/api/meetings/{m['id']}", headers=sup, json=twice).status_code == 422

    other = log(client, sup, tid, held_at=ago(days=4)).json()
    assert client.put(f"/api/meetings/{other['id']}", headers=sup, json=body(held_at=m["held_at"])).status_code == 409
    assert client.put(f"/api/meetings/{m['id']}", headers=sup, json=body(held_at=m["held_at"])).status_code == 200  # own time

    outsider = auth(client, db, "other@x.com", Role.faculty)
    assert client.put(f"/api/meetings/{m['id']}", headers=outsider, json=body()).status_code == 404
    assert client.delete(f"/api/meetings/{m['id']}", headers=outsider).status_code == 404
    assert client.put(f"/api/meetings/{m['id']}", headers=s, json=body()).status_code == 403

    assert client.delete(f"/api/meetings/{m['id']}", headers=sup).status_code == 204
    assert client.delete(f"/api/meetings/{m['id']}", headers=sup).status_code == 404
    assert client.put(f"/api/meetings/tasks/{a['id']}", headers=sup, json={"done": True}).status_code == 404
    left = client.get(f"/api/meetings/thesis/{tid}", headers=sup).json()["meetings"]
    assert [x["id"] for x in left] == [other["id"]]


def test_joined_co_supervisor_can_log_but_one_awaiting_approval_cannot(client, db):
    _, sup, co, tid = group(client, db, co=True)
    res = log(client, co, tid, co_supervisor_attended=True, supervisor_attended=False)
    assert res.status_code == 201, res.json()
    assert res.json()["recorded_by"]["id"] == me(client, co)["id"]
    assert res.json()["co_supervisor_attended"] is True


def test_co_supervisor_who_has_not_joined_sees_nothing(client, db):
    _, _, co, tid = group(client, db, co=True, co_joins=False)  # the supervisor has not approved them yet
    assert log(client, co, tid).status_code == 404
    assert client.get(f"/api/meetings/thesis/{tid}", headers=co).status_code == 404


def test_formed_group_can_log_before_p1_registration(client, db):
    s, sup, _, tid = group(client, db, register=False)
    assert log(client, sup, tid).status_code == 201
    assert len(client.get("/api/meetings/mine", headers=s).json()["meetings"]) == 1


def test_pending_group_has_no_meetings(client, db):
    s = auth(client, db, "s@x.com")
    sup = auth(client, db, "sup@x.com", Role.faculty)
    res = client.post("/api/theses/mine", headers=s, json={"supervisor_id": me(client, sup)["id"]})
    tid = res.json()["thesis"]["id"]
    assert log(client, sup, tid).status_code == 404
    mine = client.get("/api/meetings/mine", headers=s).json()
    assert (mine["thesis"], mine["meetings"], mine["can_edit"]) == (None, [], False)


def test_archived_or_completed_thesis_log_is_read_only(client, db):
    s, sup, _, tid = group(client, db)
    m = log(client, sup, tid, tasks=[{"description": "A"}]).json()
    for state in (ThesisStatus.completed, ThesisStatus.dropped):
        db.get(Thesis, tid).status = state
        db.flush()
        assert log(client, sup, tid, held_at=ago(days=7)).status_code == 409
        assert client.put(f"/api/meetings/{m['id']}", headers=sup, json=body()).status_code == 409
        assert client.delete(f"/api/meetings/{m['id']}", headers=sup).status_code == 409
        assert client.put(f"/api/meetings/tasks/{m['tasks'][0]['id']}", headers=sup, json={"done": True}).status_code == 409
        listing = client.get(f"/api/meetings/thesis/{tid}", headers=sup).json()
        assert listing["can_edit"] is False and "read-only" in listing["log_block"]
        assert len(listing["meetings"]) == 1  # still readable
