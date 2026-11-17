from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.milestone import GroupMilestone, MilestoneTemplate, Phase
from app.models.proposal import Proposal
from app.models.user import Role, User
from app.schemas import milestone as milestone_schema
from app.services import milestone_service
from app.services.progress_service import current_semester_id
from tests.helpers import PDF, auth, close_registration, form_group, me, student, supervised_student, upload

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
    set_past(db, "P1", datetime.now(timezone.utc) - timedelta(minutes=5), grace=1)
    p1 = by_phase(client.get("/api/milestones", headers=coord))["P1"]
    assert (p1["status"], p1["countdown_to"], p1["countdown_label"]) == ("grace", p1["closes_at"], "Grace ends in")


def test_penalty_can_only_be_lowered_after_the_due_date(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    close_registration(db)
    due = datetime.now(timezone.utc) - timedelta(minutes=5)
    set_past(db, "P2", due, grace=2, penalty=10)
    # Raising it would make work already handed in late cost more.
    res = put(client, coord, "P2", due, grace=2, penalty=20)
    assert (res.status_code, res.json()["detail"]) == (422, "The due date has passed, so the late penalty can only be lowered now")
    assert by_phase(put(client, coord, "P2", due, grace=2, penalty=5))["P2"]["penalty_per_day"] == 5
    # Moving the due date into the future makes nobody late, so any penalty is fine again.
    assert by_phase(put(client, coord, "P2", F, penalty=30))["P2"]["penalty_per_day"] == 30


def set_past(db, phase, due_at, grace=0, penalty=10):
    # The API refuses due dates in the past, so tests that start mid-grace write the deadline directly.
    db.merge(MilestoneTemplate(semester_id=current_semester_id(db), phase=Phase(phase), due_at=due_at, grace_days=grace, penalty_per_day=penalty))
    db.flush()


def put(client, h, phase, due_at, grace=0, penalty=10, semester_id=None):
    local = due_at.astimezone(milestone_schema.DHAKA).replace(tzinfo=None)
    # Tagged with the current semester unless a test picks another.
    semester_id = semester_id or client.get("/api/semesters/current", headers=h).json().get("id")
    body = {"due_local": local.isoformat(), "grace_days": grace, "penalty_per_day": penalty, "semester_id": semester_id}
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
    # Only due_local is taken, always as Dhaka time: an old-style due_at or a zoned due_local is refused, not guessed.
    sid = client.get("/api/semesters/current", headers=coord).json()["id"]
    send = lambda body: client.put(
        "/api/milestones/P1", headers=coord, json={"grace_days": 0, "penalty_per_day": 0, "semester_id": sid, **body}
    )
    # Every deadline is tagged with a semester that exists.
    assert put(client, coord, "P1", F, semester_id=10**6).json()["detail"] == "Pick the semester this deadline is for"
    assert send({"due_at": "2099-11-01T23:59"}).status_code == 422
    assert send({"due_local": "2099-11-01T23:59+00:00"}).status_code == 422
    # Grace days past year 9999 would overflow: a 422, not a 500.
    assert send({"due_local": "9999-12-31T23:59", "grace_days": 7}).status_code == 422
    p1 = by_phase(send({"due_local": "2099-11-01T20:30"}))["P1"]
    assert (p1["due_at"][:16], p1["due_date"], p1["due_time"]) == ("2099-11-01T14:30", "2099-11-01", "20:30")
    assert (p1["semester_id"], p1["semester_name"]) == (sid, "Current Semester")
    p2 = by_phase(send({"due_local": "2099-11-01T20:30"}))["P2"]  # not set: form defaults to end of day
    assert (p2["due_date"], p2["due_time"]) == (None, "23:59")
    # A deadline that is already over would freeze the whole phase.
    now = datetime.now(timezone.utc)
    res = put(client, coord, "P2", now - timedelta(days=2), grace=1)
    assert (res.status_code, res.json()["detail"]) == (422, "The deadline and grace period must end in the future")
    # Due already passed but grace still open: everyone would be late at once.
    res = put(client, coord, "P2", now - timedelta(hours=1), grace=1)
    assert (res.status_code, res.json()["detail"]) == (422, "The due date must be in the future")
    # P1 registration is open for this week, so P1 can't be due inside it.
    res = put(client, coord, "P1", now + timedelta(days=2))
    assert (res.status_code, res.json()["detail"]) == (422, "P1 can't be due before Current Semester's P1 registration closes")
    assert put(client, coord, "P1", now + timedelta(days=8)).status_code == 200

    res = put(client, coord, "P1", F, grace=2)
    assert res.status_code == 200
    assert (res.json()["registration_closes_at"] is not None, res.json()["registration_open"]) == (True, True)
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
    set_past(db, "P1", now - timedelta(days=3) + timedelta(minutes=1), grace=4, penalty=15)  # ~3 days into grace
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

    # Same passed due date: the coordinator may still lower the penalty during grace (raising it is refused).
    assert put(client, coord, "P1", now - timedelta(days=3) + timedelta(minutes=1), grace=4, penalty=5).status_code == 200
    assert by_phase(client.get("/api/milestones", headers=s))["P1"]["penalty_percent"] == 15  # 3 x 5%
    set_past(db, "P1", now - timedelta(days=3) + timedelta(minutes=1), grace=4, penalty=40)
    assert by_phase(client.get("/api/milestones", headers=s))["P1"]["penalty_percent"] == 100  # 3 x 40% capped

    # Grace over and never submitted: a missed deadline, not a late one.
    m = db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db)))
    m.due_at, m.grace_days, m.penalty_per_day = now - timedelta(days=3), 1, 15
    for h in (other, no_group):
        if thesis := db.get(User, me(client, h)["id"]).thesis:
            thesis.phase_started_at = now - timedelta(days=5)
    db.flush()
    rows = by_phase(client.get("/api/milestones", headers=other))
    assert (rows["P1"]["status"], rows["P1"]["submission_status"]) == ("closed", "not_submitted")
    assert (rows["P1"]["late_days"], rows["P1"]["penalty_percent"]) == (None, None)
    assert rows["P1"]["submitted_at"] is None  # another student's uploads don't count for this one

    # No thesis group, so no phase: nothing was due.
    rows = by_phase(client.get("/api/milestones", headers=no_group))
    assert (rows["P1"]["mine"], rows["P1"]["submission_status"]) == (False, None)

    # Signed up after grace ended: no thesis group yet, so nothing was due: no late days or penalty.
    late = by_phase(client.get("/api/milestones", headers=auth(client, db, "late@x.com")))["P1"]
    assert (late["mine"], late["submission_status"], late["late_days"]) == (False, None, None)


def test_each_group_gets_its_own_milestone_and_extension(client, db):
    # MilestoneTemplate is the coordinator's deadline; GroupMilestone is one group's copy; its Deliverable is the
    # version that counts (the latest upload).
    (s, _), other = supervised_student(client, db, "s@x.com"), student(client, db, "o@x.com")
    close_registration(db)
    now = datetime.now(timezone.utc)
    set_past(db, "P1", now - timedelta(hours=1), grace=1, penalty=10)  # in grace

    v1 = upload(client, s).json()["versions"][0]
    v2 = upload(client, s, content=PDF + b"2").json()["versions"][0]
    thesis_id = db.get(User, me(client, s)["id"]).thesis_id
    gm = db.scalar(select(GroupMilestone).filter_by(thesis_id=thesis_id))
    assert gm.phase == Phase.P1 and gm.extended_due_at is None
    assert gm.deliverable.proposal_version_id == v2["id"] and gm.submitted_at == gm.deliverable.proposal_version.created_at
    assert db.scalar(select(Proposal).filter_by(thesis_id=thesis_id)).versions[0].id == v2["id"]
    row = by_phase(client.get("/api/milestones", headers=s))["P1"]
    assert row["submitted_at"] is not None
    assert (row["late_days"], row["penalty_percent"]) == (1, 10)

    # Re-uploading v1's file unchanged is a new version, and it becomes the deliverable.
    before = gm.submitted_at
    v3 = upload(client, s).json()["versions"][0]
    db.refresh(gm)
    assert v3["id"] not in (v1["id"], v2["id"]) and v3["version_no"] == 3
    assert gm.deliverable.proposal_version_id == v3["id"] and gm.submitted_at > before

    # An extension moves only this group's due date: no late days for them, the other group is still late.
    gm.extended_due_at = now + timedelta(days=2)
    db.flush()
    mine_row = by_phase(client.get("/api/milestones", headers=s))["P1"]
    other_row = by_phase(client.get("/api/milestones", headers=other))["P1"]
    assert (mine_row["status"], mine_row["late_days"], mine_row["submission_status"]) == ("open", 0, "on_time")
    assert (other_row["status"], other_row["submission_status"]) == ("grace", "late")

    # Moving the deadline past the extension never leaves this group with less time than everyone else.
    db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))).due_at = now + timedelta(days=5)
    db.flush()
    assert by_phase(client.get("/api/milestones", headers=s))["P1"]["due_at"] == by_phase(
        client.get("/api/milestones", headers=other))["P1"]["due_at"]


def test_an_on_time_submission_is_final_once_the_due_date_passes(client, db):
    (s, _) = supervised_student(client, db, "s@x.com")
    close_registration(db)
    now = datetime.now(timezone.utc)
    set_past(db, "P1", now + timedelta(hours=1), grace=2, penalty=10)
    assert upload(client, s).status_code == 201
    assert upload(client, s, content=PDF + b"2").status_code == 201  # before the due date: still free to replace it

    thesis_id = db.get(User, me(client, s)["id"]).thesis_id
    gm = db.scalar(select(GroupMilestone).filter_by(thesis_id=thesis_id))
    db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))).due_at = gm.submitted_at  # due at the moment they submitted: now in grace
    db.flush()
    res = upload(client, s, content=PDF + b"3")
    assert (res.status_code, res.json()["detail"]) == (
        409, "You submitted P1 on time, so it is final now that the due date has passed"
    )
    assert client.get("/api/proposals/mine", headers=s).json()["upload_block"] == res.json()["detail"]
    row = by_phase(client.get("/api/milestones", headers=s))["P1"]
    assert (row["submission_status"], row["late_days"], row["penalty_percent"]) == ("on_time", 0, 0)


def test_extension_keeps_upload_open_and_blocks_rollover_after_template_grace(client, db):
    from app.services import progress_service

    coord = auth(client, db, "c@x.com", Role.coordinator)
    s, other = student(client, db, "s@x.com"), student(client, db, "o@x.com")
    close_registration(db)
    now = datetime.now(timezone.utc)
    put(client, coord, "P1", F, grace=1)
    db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))).due_at = now - timedelta(days=3)  # template grace ended yesterday
    user = db.get(User, me(client, s)["id"])
    # Extension granted before any submission: the group milestone is made for it.
    progress_service.group_milestone(db, user, create=True).extended_due_at = now + timedelta(days=1)
    db.flush()

    assert upload(client, s).status_code == 201  # extension reopens upload for this group only
    assert upload(client, other).status_code == 409
    res = client.post("/api/milestones/next-semester", headers=coord)
    assert (res.status_code, res.json()["detail"]) == (409, "A deadline extension for P1 is still running, wait until it ends")
    assert by_phase(client.get("/api/milestones", headers=s))["P1"]["submission_status"] == "on_time"


def test_keeping_a_passed_due_date_set_with_seconds(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    close_registration(db)
    due = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(second=42, microsecond=123)
    set_past(db, "P1", due, grace=1)
    # The form sends whole minutes; the same minute keeps the stored due date.
    assert put(client, coord, "P1", due.replace(second=0, microsecond=0), grace=2).status_code == 200
    db.expire_all()
    assert (db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))).due_at, db.get(MilestoneTemplate, (Phase.P1, current_semester_id(db))).grace_days) == (due, 2)


def test_coordinator_sets_the_p1_registration_window(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    sup = auth(client, db, "sup@x.com", Role.faculty)
    s = auth(client, db, "s@x.com")
    now = datetime.now(timezone.utc)
    local = lambda at: at.astimezone(milestone_schema.DHAKA).replace(tzinfo=None).isoformat(timespec="minutes")
    send = lambda h, opens, closes: client.put(
        "/api/milestones/registration", headers=h, json={"opens_local": local(opens), "closes_local": local(closes)}
    )

    # Unset: one week from the semester start, as before.
    res = client.get("/api/milestones", headers=coord).json()
    assert (res["registration_status"], res["registration_opens_local"] is not None) == ("open", True)

    assert send(s, now, now + timedelta(days=3)).status_code == 403
    res = send(coord, now + timedelta(days=3), now + timedelta(days=1))
    assert (res.status_code, res.json()["detail"]) == (422, "P1 registration must close after it opens")
    assert put(client, coord, "P1", now + timedelta(days=10)).status_code == 200
    res = send(coord, now + timedelta(days=1), now + timedelta(days=11))
    assert (res.status_code, res.json()["detail"]) == (422, "P1 registration must close before P1 is due")

    # Opens later: not open yet, and the group is told so.
    res = send(coord, now + timedelta(days=1), now + timedelta(days=3))
    assert res.status_code == 200
    assert (res.json()["registration_open"], res.json()["registration_closes_local"]) == (False, local(now + timedelta(days=3)))
    form_group(client, db, s, sup)
    assert client.get("/api/milestones", headers=s).json()["registration_status"] == "upcoming"
    assert client.get("/api/theses/mine", headers=s).json()["registration_upcoming"] is True
    res = client.post("/api/theses/mine/register", headers=s)
    assert (res.status_code, res.json()["detail"]) == (409, "P1 registration hasn't opened yet")

    # Open now: the group can register.
    assert send(coord, now - timedelta(hours=1), now + timedelta(days=3)).status_code == 200
    assert client.post("/api/theses/mine/register", headers=s).status_code == 200


def test_an_empty_semesters_table_gets_a_current_semester(client, db):
    # The migration makes the first semester; if the row is gone, startup makes one so registration and uploads work.
    from sqlalchemy import delete as sql_delete
    from app.models.semester import Semester
    from app.services import progress_service

    coord = auth(client, db, "c@x.com", Role.coordinator)
    db.execute(sql_delete(Semester))
    db.flush()
    assert client.get("/api/milestones", headers=coord).json()["registration_status"] == "not_set"
    progress_service.ensure_semester(db)
    assert client.get("/api/milestones", headers=coord).json()["registration_status"] == "open"
    res = client.put("/api/milestones/registration", headers=coord,
                     json={"opens_local": "2099-01-01T09:00", "closes_local": "2099-01-08T23:59"})
    assert (res.status_code, res.json()["registration_status"]) == (200, "upcoming")
    # Year 1 in Dhaka is BC in UTC: stored fine, unreadable after, so it's refused up front.
    res = client.put("/api/milestones/registration", headers=coord,
                     json={"opens_local": "0001-01-01T00:00", "closes_local": "2099-01-08T23:59"})
    assert res.status_code == 422
    assert client.get("/api/milestones", headers=coord).status_code == 200
