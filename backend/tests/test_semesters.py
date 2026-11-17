from app.models.user import Role
from tests.helpers import auth


def test_coordinator_creates_semester_and_toggles_all_steps(client, db):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    student = auth(client, db, "s@x.com", Role.student)

    # Students cannot create semesters or toggle steps
    assert client.post("/api/semesters", headers=student, json={"name": "Fall 2026"}).status_code == 403
    assert client.patch("/api/semesters/current/steps/defense", headers=student, json={"is_open": True}).status_code == 403

    # Coordinator creates a new semester with custom initial step states
    res = client.post(
        "/api/semesters",
        headers=coord,
        json={
            "name": "Fall 2026",
            "form_group_open": True,
            "pick_supervisor_open": False,
            "p1_open": True,
            "p2_open": False,
            "p3_open": False,
            "defense_open": False,
        },
    )
    assert res.status_code == 201
    body = res.json()
    assert body["name"] == "Fall 2026"
    assert body["form_group_open"] is True
    assert body["pick_supervisor_open"] is False
    assert body["defense_open"] is False
    assert [s["key"] for s in body["steps"]] == ["form_group", "pick_supervisor", "P1", "P2", "P3", "defense"]

    # Toggle each step open and closed
    for step in ("form_group", "pick_supervisor", "P1", "P2", "P3", "defense"):
        opened = client.patch(f"/api/semesters/current/steps/{step}", headers=coord, json={"is_open": True})
        assert opened.status_code == 200
        steps_map = {s["key"]: s["is_open"] for s in opened.json()["steps"]}
        assert steps_map[step] is True

        closed = client.patch(f"/api/semesters/current/steps/{step}", headers=coord, json={"is_open": False})
        assert closed.status_code == 200
        steps_map = {s["key"]: s["is_open"] for s in closed.json()["steps"]}
        assert steps_map[step] is False

    # Invalid step key returns 422
    assert client.patch("/api/semesters/current/steps/invalid_step", headers=coord, json={"is_open": True}).status_code == 422


def test_closing_steps_blocks_student_actions(client, db, timelines):
    coord = auth(client, db, "c@x.com", Role.coordinator)
    s1 = auth(client, db, "s1@x.com", Role.student)

    # Close group formation -> creating a group returns 409
    assert client.patch("/api/semesters/current/steps/form_group", headers=coord, json={"is_open": False}).status_code == 200
    res = client.post("/api/groups/mine", headers=s1, json={"name": "Blocked Team"})
    assert res.status_code == 409
    assert "closed" in res.json()["detail"].lower()

    # Re-open group formation -> creating a group succeeds
    assert client.patch("/api/semesters/current/steps/form_group", headers=coord, json={"is_open": True}).status_code == 200
    assert client.post("/api/groups/mine", headers=s1, json={"name": "Allowed Team"}).status_code == 201