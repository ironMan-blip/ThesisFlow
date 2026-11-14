from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.milestone import GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import Proposal
from app.models.user import Role, User
from app.services import milestone_service
from tests.helpers import PDF, auth, close_registration, me, student, upload

T = datetime(2026, 11, 1, 23, 59, tzinfo=timezone.utc)
F = datetime(2099, 11, 1, 23, 59, tzinfo=timezone.utc)  # a deadline far in the future


def test_late_days_with_fixed_clock():
    assert milestone_service.late_days(T, T) == 0
    assert milestone_service.late_days(T, T - timedelta(hours=5)) == 0
    assert milestone_service.late_days(T, T + timedelta(minutes=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1)) == 1
    assert milestone_service.late_days(T, T + timedelta(days=1, seconds=1)) == 2


def test_grace_countdown_targets_closes_at(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    close_registration(db)
    put(client, coord, "P1", datetime.now(timezone.utc) - timedelta(minutes=5), grace=1)
    p1 = by_phase(client.get("/api/milestones", headers=coord))["P1"]
    assert (p1["status"], p1["countdown_to"], p1["countdown_label"]) == ("grace", p1["closes_at"], "Grace ends in")


def put(client, h, phase, due_at, grace=0, penalty=10):
    body = {"due_at": due_at.isoformat(), "grace_days": grace, "penalty_per_day": penalty}
    return client.put(f"/api/milestones/{phase}", headers=h, json=body)


def by_phase(res):
    return {m["phase"]: m for m in res.json()["milestones"]}


def test_only_coordinator_sets_deadlines_and_input_is_checked(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    student = auth(client, db, "s@x.com")
    assert put(client, student, "P1", F).status_code == 403
    assert put(client, coord, "P4", F).status_code == 422
    assert put(client, coord, "P1", F, penalty=101).status_code == 422
    assert put(client, coord, "P1", F, grace=-1).status_code == 422
    naive = {"due_at": "2099-11-01T23:59:00", "grace_days": 0, "penalty_per_day": 0}
    assert client.put("/api/milestones/P1", headers=coord, json=naive).status_code == 422
    # A deadline that is already over would freeze the whole phase.
    now = datetime.now(timezone.utc)
    res = put(client, coord, "P2", now - timedelta(days=2), grace=1)
    assert (res.status_code, res.json()["detail"]) == (422, "The deadline and grace period must end in the future")
    # P1 registration is open for this week, so P1 can't be due inside it.
    res = put(client, coord, "P1", now + timedelta(days=2))
    assert (res.status_code, res.json()["detail"]) == (422, "P1 can't be due before P1 registration closes")
    assert put(client, coord, "P1", now + timedelta(days=8)).status_code == 200

    res = put(client, coord, "P1", F, grace=2)
    assert res.status_code == 200
    assert res.json()["registration_closes_at"] is not None
    p1 = by_phase(res)["P1"]
    assert p1["closes_at"].startswith("2099-11-03T23:59")
    assert p1["late_days"] is None and p1["submission_status"] is None  # staff get no personal late count
    assert by_phase(res)["P2"]["status"] == "not_set"
    assert res.json()["can_edit"] is True
    assert client.get("/api/milestones", headers=student).json()["can_edit"] is False

    put(client, coord, "P1", F + timedelta(days=1))  # setting again replaces it
    assert by_phase(client.get("/api/milestones", headers=student))["P1"]["due_at"].startswith("2099-11-02T23:59")


def test_phase_deadlines_need_not_be_in_order(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    assert put(client, coord, "P2", F).status_code == 200
    assert put(client, coord, "P1", F + timedelta(days=1)).status_code == 200
    assert put(client, coord, "P3", F - timedelta(days=1)).status_code == 200


def test_student_late_days_and_penalty(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s = student(client, db, "s@x.com")
    other = student(client, db, "o@x.com")
    no_group = auth(client, db, "n@x.com")  # signed up in time but never got a group accepted
    close_registration(db)
    now = datetime.now(timezone.utc)
    put(client, coord, "P1", now - timedelta(days=3) + timedelta(minutes=1), grace=4, penalty=15)  # ~3 days into grace
    put(client, coord, "P2", now + timedelta(days=5), penalty=10)

    rows = by_phase(client.get("/api/milestones", headers=s))
    assert (rows["P1"]["mine"], rows["P2"]["mine"]) == (True, False)  # a new student is in P1
    assert rows["P1"]["status"] == "grace" and rows["P1"]["submitted_at"] is None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)  # still counting
    assert (rows["P1"]["countdown_to"], rows["P1"]["submission_status"]) == (rows["P1"]["closes_at"], "late")
    assert (rows["P2"]["status"], rows["P2"]["late_days"], rows["P2"]["submission_status"]) == ("open", None, None)
    assert (rows["P2"]["countdown_to"], rows["P2"]["countdown_label"]) == (rows["P2"]["due_at"], "Due in")

    assert upload(client, s).status_code == 201  # late upload in grace is accepted
    rows = by_phase(client.get("/api/milestones", headers=s))
    assert rows["P1"]["submitted_at"] is not None
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (3, 45)

    put(client, coord, "P1", now - timedelta(days=3) + timedelta(minutes=1), grace=4, penalty=40)
    assert by_phase(client.get("/api/milestones", headers=s))["P1"]["penalty_percent"] == 100  # 3 x 40% capped

    # Grace over and never submitted: a missed deadline, not a late one.
    m = db.get(MilestoneTemplate, Phase.P1)
    m.due_at, m.grace_days, m.penalty_per_day = now - timedelta(days=3), 1, 15
    for h in (other, no_group):
        db.get(User, me(client, h)["id"]).phase_started_at = now - timedelta(days=5)
    db.flush()
    rows = by_phase(client.get("/api/milestones", headers=other))
    assert (rows["P1"]["status"], rows["P1"]["submission_status"]) == ("closed", "not_submitted")
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (None, None)
    assert rows["P1"]["submitted_at"] is None  # another student's uploads don't count for this one

    # No accepted group, so they couldn't upload: nothing was due.
    rows = by_phase(client.get("/api/milestones", headers=no_group))
    assert (rows["P1"]["mine"], rows["P1"]["submission_status"]) == (True, None)

    # Signed up after grace ended: nothing was due, so no late days or penalty.
    late = by_phase(client.get("/api/milestones", headers=auth(client, db, "late@x.com")))["P1"]
    assert (late["mine"], late["submission_status"], late["late_days"]) == (True, None, None)


def test_each_group_gets_its_own_milestone_and_extension(client, db):
    # MilestoneTemplate is the coordinator's deadline; GroupMilestone is one group's copy; its Deliverable is the
    # version that counts (the latest upload).
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s, other = student(client, db, "s@x.com"), student(client, db, "o@x.com")
    close_registration(db)
    now = datetime.now(timezone.utc)
    put(client, coord, "P1", now - timedelta(hours=1), grace=1, penalty=10)  # in grace

    v1 = upload(client, s, title="v1").json()["versions"][0]
    v2 = upload(client, s, content=PDF + b"2", title="v2").json()["versions"][0]
    thesis_id = db.get(User, me(client, s)["id"]).thesis_id
    gm = db.scalar(select(GroupMilestone).filter_by(thesis_id=thesis_id))
    assert gm.phase == Phase.P1 and gm.extended_due_at is None
    assert gm.deliverable.proposal_version_id == v2["id"] and gm.submitted_at == gm.deliverable.proposal_version.created_at
    assert db.scalar(select(Proposal).filter_by(thesis_id=thesis_id)).latest_version.id == v2["id"]
    row = by_phase(client.get("/api/milestones", headers=s))["P1"]
    assert row["submitted_at"] is not None
    assert (row["late_days"], row["penalty_percent"]) == (1, 10)

    # Re-submitting v1 unchanged makes it the deliverable again, with a new submit time.
    before = gm.submitted_at
    upload(client, s, title="v1")
    db.refresh(gm)
    assert gm.deliverable.proposal_version_id == v1["id"] and gm.submitted_at > before

    # Removing the deliverable falls back to the other upload; removing both leaves nothing submitted.
    client.delete(f"/api/proposals/versions/{v1['id']}", headers=s)
    db.refresh(gm)
    assert gm.deliverable.proposal_version_id == v2["id"]
    client.delete(f"/api/proposals/versions/{v2['id']}", headers=s)
    db.refresh(gm)
    assert (gm.deliverable, gm.submitted_at) == (None, None)
    v1 = upload(client, s, title="v1").json()["versions"][0]

    # An extension moves only this group's due date: no late days for them, the other group is still late.
    gm.extended_due_at = now + timedelta(days=2)
    db.flush()
    mine_row = by_phase(client.get("/api/milestones", headers=s))["P1"]
    other_row = by_phase(client.get("/api/milestones", headers=other))["P1"]
    assert (mine_row["status"], mine_row["late_days"], mine_row["submission_status"]) == ("open", 0, "on_time")
    assert (other_row["status"], other_row["submission_status"]) == ("grace", "late")
