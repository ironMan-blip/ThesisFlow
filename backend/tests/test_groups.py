from datetime import timedelta

from sqlalchemy import select

from app.models.group import MAX_MEMBERS, Invitation
from app.models.user import Role
from tests.helpers import REASON, auth, me, run_deletions_due


def sid(client, h):
    return me(client, h)["id"]


def mine(client, h):
    return client.get("/api/groups/mine", headers=h).json()


def invite(client, leader, other):
    return client.post("/api/groups/mine/invitations", headers=leader, json={"student_id": sid(client, other)})


def join(client, leader, other):
    assert invite(client, leader, other).status_code == 201
    inv = mine(client, other)["received_invitations"][0]
    res = client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=other)
    assert res.status_code == 200, res.json()
    return res


def create(client, h, name="Team"):
    res = client.post("/api/groups/mine", headers=h, json={"name": name})
    assert res.status_code == 201, res.json()
    return res.json()


def students(client, db, n):
    return [auth(client, db, f"s{i}@x.com") for i in range(n)]


def test_create_group_and_who_can_use_it(client, db):
    a, b = students(client, db, 2)
    state = create(client, a, "  Team Rocket ")
    assert state["group"]["name"] == "Team Rocket" and state["is_leader"] is True
    assert [m["id"] for m in state["group"]["members"]] == [sid(client, a)]
    assert (state["group"]["is_ready"], state["group"]["members_needed"], state["can_create"]) == (False, 2, False)
    assert client.post("/api/groups/mine", headers=a, json={"name": "Again"}).status_code == 409
    assert client.post("/api/groups/mine", headers=b, json={"name": "  "}).status_code == 422
    assert invite(client, b, a).status_code == 409  # b has no group yet
    assert client.get("/api/groups/mine", headers=auth(client, db, "f@x.com", Role.faculty)).status_code == 403


def test_invite_accept_and_group_becomes_ready_at_three(client, db):
    a, b, c = students(client, db, 3)
    create(client, a)
    assert join(client, a, b).json()["group"]["members_needed"] == 1
    assert client.get("/api/auth/me/counts", headers=c).json() == {}
    assert invite(client, a, c).status_code == 201
    assert client.get("/api/auth/me/counts", headers=c).json() == {"group": 1}
    assert invite(client, a, c).status_code == 409  # already invited
    assert invite(client, b, c).status_code == 403  # only the leader invites
    inv = mine(client, c)["received_invitations"][0]
    assert inv["group_name"] == "Team" and inv["member_count"] == 2
    state = client.post(f"/api/groups/invitations/{inv['id']}/accept", headers=c).json()
    assert (state["group"]["is_ready"], len(state["group"]["members"]), state["received_invitations"]) == (True, 3, [])
    assert mine(client, a)["sent_invitations"] == []


def test_group_is_capped_and_live_invitations_hold_a_spot(client, db):
    people = students(client, db, MAX_MEMBERS + 2)
    leader, rest = people[0], people[1:]
    create(client, leader)
    for h in rest[: MAX_MEMBERS - 2]:
        join(client, leader, h)  # 4 members
    assert invite(client, leader, rest[3]).status_code == 201  # the 5th spot is now reserved
    state = mine(client, leader)
    assert (state["open_slots"], state["can_invite"]) == (0, False)
    res = invite(client, leader, rest[4])
    assert res.status_code == 409 and "full" in res.json()["detail"]
    inv = state["sent_invitations"][0]
    assert client.delete(f"/api/groups/mine/invitations/{inv['id']}", headers=leader).json()["open_slots"] == 1
    assert invite(client, leader, rest[4]).status_code == 201


def test_decline_cancel_and_joining_cancels_other_invitations(client, db):
    a, b, c = students(client, db, 3)
    create(client, a, "A")
    create(client, b, "B")
    d = auth(client, db, "d@x.com")
    invite(client, a, d)
    invite(client, b, d)
    first, second = mine(client, d)["received_invitations"]
    assert client.post(f"/api/groups/invitations/{first['id']}/decline", headers=d).status_code == 200
    assert client.post(f"/api/groups/invitations/{first['id']}/accept", headers=d).status_code == 404
    assert client.post(f"/api/groups/invitations/{second['id']}/accept", headers=c).status_code == 404  # not theirs
    invite(client, a, d)  # a may ask again after a decline
    client.post(f"/api/groups/invitations/{second['id']}/accept", headers=d)
    state = mine(client, d)
    assert state["group"]["name"] == "B" and state["received_invitations"] == []
    assert client.get("/api/auth/me/counts", headers=d).json() == {}


def test_invitation_expires_after_three_days(client, db):
    a, b = students(client, db, 2)
    create(client, a)
    invite(client, a, b)
    inv = db.scalar(select(Invitation))
    inv.created_at -= timedelta(days=3, minutes=1)
    db.flush()
    assert mine(client, b)["received_invitations"] == [] and mine(client, a)["sent_invitations"] == []
    assert client.get("/api/auth/me/counts", headers=b).json() == {}
    assert client.post(f"/api/groups/invitations/{inv.id}/accept", headers=b).status_code == 404
    assert invite(client, a, b).status_code == 201  # the lapsed one no longer blocks a new one


def test_leaving_passes_leadership_and_last_member_removes_group(client, db):
    a, b, c = students(client, db, 3)
    create(client, a)
    join(client, a, b)
    join(client, a, c)
    state = client.delete("/api/groups/mine", headers=a).json()
    assert state["group"] is None and state["can_create"] is True
    state = mine(client, b)
    assert state["is_leader"] is True and len(state["group"]["members"]) == 2
    client.delete("/api/groups/mine", headers=b)
    client.delete("/api/groups/mine", headers=c)
    assert db.scalar(select(Invitation)) is None
    assert client.delete("/api/groups/mine", headers=c).status_code == 409
    assert client.post("/api/groups/mine", headers=a, json={"name": "New"}).status_code == 201


def test_profile_and_teammate_search(client, db):
    a, b, c, d = students(client, db, 4)
    body = {"interests": ["NLP ", "Computer Vision", "nlp"], "skills": ["Python"], "bio": "hi", "open_to_invites": True}
    res = client.put("/api/groups/profile", headers=b, json=body)
    assert (res.json()["interests"], res.json()["skills"]) == (["nlp", "computer vision"], ["python"])
    assert client.put("/api/groups/profile", headers=b, json={"skills": ["a,b"]}).status_code == 422
    client.put("/api/groups/profile", headers=c, json={"interests": ["nlp"], "open_to_invites": False})
    assert client.get("/api/groups/profile", headers=d).json()["interests"] == []
    create(client, a)

    found = lambda q: [r["id"] for r in client.get("/api/groups/teammates", params={"q": q}, headers=a).json()]
    assert found("NLP") == [sid(client, b)]  # c hides themselves
    assert found("python") == [sid(client, b)]
    assert set(found("")) == {sid(client, b), sid(client, d)}
    assert found("%") == []  # wildcards are matched literally
    row = client.get("/api/groups/teammates", params={"q": "nlp"}, headers=a).json()[0]
    assert (row["can_invite"], row["invited"], row["interests"]) == (True, False, ["nlp", "computer vision"])
    assert invite(client, a, c).status_code == 409  # not taking invitations
    invite(client, a, b)
    row = client.get("/api/groups/teammates", params={"q": "nlp"}, headers=a).json()[0]
    assert (row["can_invite"], row["invited"]) == (False, True)
    join_inv = mine(client, b)["received_invitations"][0]
    client.post(f"/api/groups/invitations/{join_inv['id']}/accept", headers=b)
    assert found("nlp") == []  # in a group, so no longer listed
    assert client.get("/api/groups/teammates", headers=auth(client, db, "f@x.com", Role.faculty)).status_code == 403


def test_deleting_a_member_or_the_leader_keeps_the_group_working(client, db):
    a, b, c = students(client, db, 3)
    coord = auth(client, db, "c@x.com", Role.coordinator)
    create(client, a)
    join(client, a, b)
    join(client, a, c)
    assert client.post(f"/api/auth/accounts/{sid(client, a)}/deletion", headers=coord, json=REASON).status_code == 200
    run_deletions_due(db)
    state = mine(client, b)
    assert state["group"]["leader"]["id"] == sid(client, b)
    assert sorted(m["id"] for m in state["group"]["members"]) == sorted([sid(client, b), sid(client, c)])
