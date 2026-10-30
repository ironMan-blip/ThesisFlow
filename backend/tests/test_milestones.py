from datetime import datetime, timedelta, timezone

from app.models.user import Role
from app.services import milestone_service
from tests.helpers import PDF, auth, upload

T = datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)


def test_late_days_with_fixed_clock():
    assert milestone_service.late_days(T, T) == 0
    assert milestone_service.late_days(T, T - timedelta(hours=5)) == 0
    assert milestone_service.late_days(T, T + timedelta(minutes=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1, seconds=1)) == 2


def test_grace_countdown_targets_closes_at(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    put(client, coord, "P1", datetime.now(timezone.utc) - timedelta(minutes=5), grace=60)
    p1 = by_phase(client.get("/api/milestones", headers=coord))["P1"]
    assert (p1["status"], p1["countdown_to"], p1["countdown_label"]) == ("grace", p1["closes_at"], "Grace ends in")


def put(client, h, phase, due_at, grace=0, penalty=10):
    body = {"due_at": due_at.isoformat(), "grace_minutes": grace, "penalty_per_day": penalty}
    return client.put(f"/api/milestones/{phase}", headers=h, json=body)


def by_phase(res):
    return {m["phase"]: m for m in res.json()["milestones"]}


def test_only_coordinator_sets_deadlines_and_input_is_checked(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    student = auth(client, db, "s@x.com")
    assert put(client, student, "P1", T).status_code == 403
    assert put(client, coord, "P4", T).status_code == 422
    assert put(client, coord, "P1", T, penalty=101).status_code == 422
    assert put(client, coord, "P1", T, grace=-1).status_code == 422
    naive = {"due_at": "2026-11-01T23:59:00", "grace_minutes": 0, "penalty_per_day": 0}
    assert client.put("/api/milestones/P1", headers=coord, json=naive).status_code == 422

    res = put(client, coord, "P1", T, grace=30)
    assert res.status_code == 200
    p1 = by_phase(res)["P1"]
    assert p1["closes_at"].startswith("2026-11-02T00:29")
    assert p1["late_days"] is None and p1["submission_status"] is None  # staff get no personal late count
    assert by_phase(res)["P2"]["status"] == "not_set"
    assert res.json()["can_edit"] is True
    assert client.get("/api/milestones", headers=student).json()["can_edit"] is False

    put(client, coord, "P1", T + timedelta(days=1))  # setting again replaces it
    assert by_phase(client.get("/api/milestones", headers=student))["P1"]["due_at"].startswith("2026-11-02T23:59")


def test_phase_deadlines_must_be_in_order(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    assert put(client, coord, "P2", T).status_code == 200
    res = put(client, coord, "P1", T + timedelta(minutes=1))
    assert (res.status_code, res.json()["detail"]) == (409, "P1 deadline can't be after P2")
    assert put(client, coord, "P3", T - timedelta(days=1)).json()["detail"] == "P3 deadline can't be before P2"
    assert put(client, coord, "P3", T).status_code == 200  # same time is fine
    assert put(client, coord, "P2", T + timedelta(days=1)).json()["detail"] == "P2 deadline can't be after P3"
    assert put(client, coord, "P1", T - timedelta(days=1)).status_code == 200
    assert put(client, coord, "P3", T - timedelta(days=2)).json()["detail"] == "P3 deadline can't be before P1"


def test_student_late_days_and_penalty(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    student = auth(client, db, "s@x.com")
    now = datetime.now(timezone.utc)
    put(client, coord, "P1", now - timedelta(days=3), grace=60, penalty=15)  # closed ~2d23h ago
    put(client, coord, "P2", now + timedelta(days=5), penalty=10)

    rows = by_phase(client.get("/api/milestones", headers=student))
    assert rows["P1"]["status"] == "closed" and rows["P1"]["submitted_at"] is None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)  # still counting
    assert (rows["P2"]["status"], rows["P2"]["late_days"]) == ("open", 0)
    assert (rows["P1"]["countdown_to"], rows["P1"]["submission_status"]) == (None, "late")
    assert (rows["P2"]["countdown_to"], rows["P2"]["countdown_label"]) == (rows["P2"]["due_at"], "Due in")
    assert rows["P2"]["submission_status"] == "not_submitted"

    assert upload(client, student, phase="P1").status_code == 409  # closed phases take no uploads
    upload(client, student, content=PDF + b"p2", phase="P2")
    rows = by_phase(client.get("/api/milestones", headers=student))
    assert rows["P1"]["submitted_at"] is None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)
    assert (rows["P2"]["late_days"], rows["P2"]["penalty_percent"]) == (0, 0)
    assert rows["P2"]["submission_status"] == "on_time"

    put(client, coord, "P1", now - timedelta(days=3), grace=60, penalty=40)
    assert by_phase(client.get("/api/milestones", headers=student))["P1"]["penalty_percent"] == 100  # 3 x 40% capped

    # Another student's uploads don't count for this one.
    other = auth(client, db, "o@x.com")
    assert by_phase(client.get("/api/milestones", headers=other))["P2"]["submitted_at"] is None
