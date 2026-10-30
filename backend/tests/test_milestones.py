from datetime import datetime, timedelta, timezone

from app.models.user import Role
from app.services import milestone_service
from tests.test_proposals import auth, upload, upload_dir  # noqa: F401

T = datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)


def test_late_days_with_fixed_clock():
    assert milestone_service.late_days(T, T) == 0
    assert milestone_service.late_days(T, T - timedelta(hours=5)) == 0
    assert milestone_service.late_days(T, T + timedelta(minutes=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1, seconds=1)) == 2


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
    assert p1["late_days"] is None  # staff get no personal late count
    assert by_phase(res)["P2"]["status"] == "not_set"

    put(client, coord, "P1", T + timedelta(days=1))  # setting again replaces it
    assert by_phase(client.get("/api/milestones", headers=student))["P1"]["due_at"].startswith("2026-11-02T23:59")


def test_student_late_days_and_penalty(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    student = auth(client, db, "s@x.com")
    now = datetime.now(timezone.utc)
    put(client, coord, "P1", now - timedelta(days=3), grace=60, penalty=15)  # closed ~2d23h ago
    put(client, coord, "P2", now + timedelta(days=5), penalty=10)
    put(client, coord, "P3", now - timedelta(days=10), penalty=20)

    rows = by_phase(client.get("/api/milestones", headers=student))
    assert rows["P1"]["status"] == "closed" and rows["P1"]["submitted_at"] is None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)  # still counting
    assert (rows["P2"]["status"], rows["P2"]["late_days"]) == ("open", 0)
    assert rows["P3"]["penalty_percent"] == 100  # 10 days x 20% is capped

    upload(client, student, phase="P1")
    upload(client, student, phase="P2")
    rows = by_phase(client.get("/api/milestones", headers=student))
    assert rows["P1"]["submitted_at"] is not None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)
    assert (rows["P2"]["late_days"], rows["P2"]["penalty_percent"]) == (0, 0)

    # Another student's uploads don't count for this one.
    other = auth(client, db, "o@x.com")
    assert by_phase(client.get("/api/milestones", headers=other))["P2"]["submitted_at"] is None
