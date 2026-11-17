"""A thesis belongs to a student group: any member asks the supervisor and adds a co-supervisor, everyone shares it,
members join or leave only before P1 registration, and P3 outcomes apply to the whole group."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.milestone import MilestoneTemplate, Phase
from app.models.user import Role, User
from tests.helpers import auth, me, upload

pytestmark = pytest.mark.usefixtures("timelines")


def thesis_state(client, h):
    return client.get("/api/theses/mine", headers=h).json()


def team(client, db, n=3):
    """n logged-in students in one group (the first leads). Returns their headers."""
    hs = [auth(client, db, f"t{i}@x.com") for i in range(n)]
    assert client.post("/api/groups/mine", headers=hs[0], json={"name": "Team"}).status_code == 201
    for h in hs[1:]:
        join(client, hs[0], h)
    return hs


def join(client, leader, h):
    """Leader invites h, h accepts. Returns the accept response."""
    res = client.post("/api/groups/mine/invitations", headers=leader, json={"student_id": me(client, h)["id"]})
    assert res.status_code == 201, res.json()
    inv = client.get("/api/groups/mine", headers=h).json()["received_invitations"][0]["id"]
    return client.post(f"/api/groups/invitations/{inv}/accept", headers=h)


def ask(client, h, sup):
    return client.post("/api/theses/mine", headers=h, json={"supervisor_id": me(client, sup)["id"]})


def test_any_member_of_a_ready_group_asks_and_everyone_shares_the_thesis(client, db):
    sup, co = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "co@x.com", Role.faculty)
    lead, a = team(client, db, 2)
    assert thesis_state(client, a)["form_group_block"] == "Your group needs 1 more member before choosing a supervisor"
    assert ask(client, a, sup).status_code == 409

    b = auth(client, db, "b@x.com")
    assert join(client, lead, b).status_code == 200
    res = ask(client, a, sup)  # not the leader
    assert res.status_code == 201
    tid = res.json()["thesis"]["id"]
    assert {thesis_state(client, h)["thesis"]["id"] for h in (lead, a, b)} == {tid}
    assert len(res.json()["thesis"]["members"]) == 3
    assert ask(client, lead, sup).status_code == 409  # the group already has one

    # Another member cancels; everyone is free again.
    assert client.delete("/api/theses/mine", headers=b).status_code == 200
    assert all(thesis_state(client, h)["thesis"] is None for h in (lead, a, b))

    tid = ask(client, lead, sup).json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=sup).status_code == 204
    assert client.post("/api/theses/mine/co-supervisor", headers=b, json={"co_supervisor_id": me(client, co)["id"]}).status_code == 200
    assert thesis_state(client, a)["thesis"]["co_supervisor"]["id"] == me(client, co)["id"]
    assert client.delete("/api/theses/mine/co-supervisor", headers=a).status_code == 200


def test_members_come_and_go_before_registration_only(client, db):
    sup = auth(client, db, "sup@x.com", Role.faculty)
    lead, a, b = team(client, db)
    tid = ask(client, lead, sup).json()["thesis"]["id"]
    assert client.post(f"/api/theses/requests/{tid}/accept", headers=sup).status_code == 204

    # Before registration: a joiner shares the thesis, a leaver loses it, and registering needs the minimum size.
    c = auth(client, db, "c@x.com")
    assert join(client, lead, c).status_code == 200
    assert thesis_state(client, c)["thesis"]["id"] == tid
    assert client.delete("/api/groups/mine", headers=c).status_code == 200
    assert client.delete("/api/groups/mine", headers=b).status_code == 200
    assert thesis_state(client, b)["thesis"] is None
    state = thesis_state(client, lead)
    assert (state["can_register"], state["register_block"]) == (False, "Your group needs 1 more member to register")
    assert join(client, lead, auth(client, db, "d@x.com")).status_code == 200
    assert client.post("/api/theses/mine/register", headers=a).status_code == 200  # any member registers

    # Registered: nobody leaves or joins.
    group = client.get("/api/groups/mine", headers=a).json()
    assert (group["locked"], group["can_leave"], group["can_invite"]) == (True, False, False)
    res = client.delete("/api/groups/mine", headers=a)
    assert (res.status_code, res.json()["detail"]) == (409, "Your group is registered for P1, so members can't leave")
    res = client.post("/api/groups/mine/invitations", headers=lead, json={"student_id": me(client, auth(client, db, "e@x.com"))["id"]})
    assert res.status_code == 409


def test_last_member_out_deletes_an_unregistered_request(client, db):
    sup = auth(client, db, "sup@x.com", Role.faculty)
    hs = team(client, db)
    ask(client, hs[0], sup)
    for h in hs:
        assert client.delete("/api/groups/mine", headers=h).status_code == 200
    assert client.get("/api/theses/requests", headers=sup).json() == []


def test_p3_completes_the_thesis_for_every_member(client, db):
    sup, coord = auth(client, db, "sup@x.com", Role.faculty), auth(client, db, "c@x.com", Role.coordinator)
    hs = team(client, db)
    tid = ask(client, hs[0], sup).json()["thesis"]["id"]
    client.post(f"/api/theses/requests/{tid}/accept", headers=sup)
    client.post("/api/theses/mine/register", headers=hs[0])
    for h in hs:
        db.get(User, me(client, h)["id"]).phase = Phase.P3
    db.flush()
    assert upload(client, hs[1]).status_code == 201

    for m in db.query(MilestoneTemplate):
        m.due_at, m.grace_days = datetime.now(timezone.utc) - timedelta(minutes=5), 0
    db.flush()
    res = client.post("/api/milestones/next-semester", headers=coord).json()
    assert res["completed"] == 3
    assert [me(client, h)["phase"] for h in hs] == [None, None, None]
    assert thesis_state(client, hs[2])["thesis"]["status"] == "completed"
