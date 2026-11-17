from datetime import timedelta

import pytest
from fastapi import HTTPException
from redis import Redis
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import rate_limit
from app.config import settings
from app.database import get_db
from app.main import app
from app.models.user import Role, User
from app.security import hash_password
from app.services import account_service, auth_service
from app.services.auth_service import REGISTER_TAKEN
from tests.helpers import REASON, auth, run_deletions_due, student as make_student, supervised_student, upload


def register(client, email=None, password="Password123", id_number="12345678", role="student", initials=None):
    if initials is None and role == "faculty":
        initials = "ABC"
    if email is None:
        email = "a@bracu.ac.bd" if role == "faculty" else "a@g.bracu.ac.bd"
    return client.post(
        "/api/auth/register",
        json={
            "email": email, "id_number": id_number, "full_name": "A", "password": password, "role": role,
            "initials": initials,
        },
    )


def login(client, id_number="12345678", password="Password123"):
    return client.post("/api/auth/login", data={"username": id_number, "password": password})


def test_register_login_me(client, db):
    r = register(client)
    assert r.status_code == 201 and r.json()["approved"] is False
    assert login(client).status_code == 403
    db.get(User, r.json()["id"]).approved = True
    db.commit()
    token = login(client).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"
    assert me.json()["tools"] == ["group", "teammates", "thesis", "proposal", "deadlines", "meetings", "account"]
    assert me.json()["phase"] == "P1"  # every student starts at P1
    assert me.json()["review_hours"] == 48


def test_duplicate_email_rejected(client, db):
    auth_service.create_user(db, "a@g.bracu.ac.bd", "12345678", "A", "Password123", Role.student)
    r = register(client, email="A@G.BRACU.AC.BD", id_number="87654321")
    assert r.status_code == 409
    assert r.json()["detail"] == REGISTER_TAKEN


def test_register_needs_bracu_email_for_role(client):
    # Students sign up with @g.bracu.ac.bd, faculty with @bracu.ac.bd; neither domain works for the other role.
    for email, role in [("a@gmail.com", "student"), ("a@bracu.ac.bd", "student"),
                        ("a@gmail.com", "faculty"), ("a@g.bracu.ac.bd", "faculty"), ("a@xbracu.ac.bd", "faculty")]:
        r = register(client, email=email, role=role)
        assert r.status_code == 422 and r.json()["detail"].startswith("email:"), (email, role)
    assert register(client, email="A@G.BRACU.AC.BD").status_code == 201
    assert register(client, email="f@bracu.ac.bd", id_number="87654321", role="faculty").status_code == 201


def test_duplicate_id_number_rejected(client, db):
    auth_service.create_user(db, "a@b.com", "12345678", "A", "Password123", Role.student)
    for role in ["student", "faculty"]:
        r = register(client, role=role)
        assert r.status_code == 409
        assert r.json()["detail"] == REGISTER_TAKEN


def test_login_needs_id_number_not_email(client):
    register(client)
    assert login(client, id_number="a@b.com").status_code == 401
    assert login(client, id_number="99999999").status_code == 401


def test_wrong_password_rejected(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_works_for_seeded_reserved_domain(client, db):
    auth_service.create_user(db, "student@thesisflow.test", "10000001", "S", "Password123", Role.student)
    token = login(client, id_number="10000001").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "student@thesisflow.test"


def test_coordinator_signup_rejected(client):
    assert register(client, role="coordinator").status_code == 422


def test_faculty_initials(client, db):
    for bad in ["", "abc", "AB1", "A B", "ABCDEFGHIJK"]:
        assert register(client, role="faculty", initials=bad).status_code == 422
    r = register(client, role="faculty", initials="MMR")
    assert r.status_code == 201 and r.json()["initials"] == "MMR"
    r = register(client, email="x@bracu.ac.bd", id_number="87654321", role="faculty", initials="MMR")
    assert r.status_code == 409 and r.json()["detail"] == "Initials already registered"
    # Students never carry initials.
    r = register(client, email="s@g.bracu.ac.bd", id_number="11111111", initials="ZZ")
    assert r.status_code == 201 and r.json()["initials"] is None


def test_expired_request_frees_initials(client, db):
    old_id = register(client, role="faculty", initials="MMR").json()["id"]
    db.get(User, old_id).created_at -= timedelta(hours=48, minutes=1)
    db.commit()
    r = register(client, email="x@bracu.ac.bd", id_number="87654321", role="faculty", initials="MMR")
    assert r.status_code == 201 and db.get(User, old_id) is None


def test_parallel_signup_gives_409(client, db, monkeypatch):
    assert register(client, role="faculty", initials="MMR").status_code == 201
    # Simulate a parallel sign-up: the pre-checks see nothing, the unique constraint catches it.
    monkeypatch.setattr(auth_service, "get_by_id_number", lambda db, n: None)
    monkeypatch.setattr(auth_service, "get_by_email", lambda db, e: None)
    r = register(client, email="x@bracu.ac.bd", role="faculty", initials="ZZ")
    assert r.status_code == 409 and r.json()["detail"].startswith("Email, ID number or initials")


def test_signups_wait_for_approval(client, db):
    r = register(client, email="f@bracu.ac.bd", role="faculty")
    assert r.status_code == 201 and r.json()["approved"] is False
    assert login(client).status_code == 403
    assert register(client, email="s@g.bracu.ac.bd", id_number="33333333").json()["approved"] is False

    coord = auth(client, db, "coord@b.com", Role.coordinator)
    student = auth(client, db, "s@b.com")
    assert client.get("/api/auth/registration-requests", headers=student).status_code == 403
    pending = client.get("/api/auth/registration-requests", headers=coord).json()
    assert [(p["email"], p["role"]) for p in pending] == [("f@bracu.ac.bd", "faculty"), ("s@g.bracu.ac.bd", "student")]

    for p in pending:
        assert client.post(f"/api/auth/registration-requests/{p['id']}/approve", headers=coord).status_code == 200
    assert login(client).status_code == 200
    assert login(client, id_number="33333333").status_code == 200
    assert client.get("/api/auth/registration-requests", headers=coord).json() == []
    # Already approved, so no longer a request.
    uid = pending[0]["id"]
    assert client.delete(f"/api/auth/registration-requests/{uid}", headers=coord).status_code == 404


def test_reject_frees_email(client, db):
    body = {"email": "f@bracu.ac.bd", "id_number": "22222222", "full_name": "F", "password": "Password123", "role": "faculty", "initials": "FB"}
    uid = client.post("/api/auth/register", json=body).json()["id"]
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert client.delete(f"/api/auth/registration-requests/{uid}", headers=coord).status_code == 204
    assert client.post("/api/auth/register", json=body).status_code == 201


def test_ensure_admin_creates_and_resets(client, db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "Admin@B.com")
    monkeypatch.setattr(settings, "admin_id_number", "00000000")
    monkeypatch.setattr(settings, "admin_password", "first-pass1")
    auth_service.ensure_admin(db)
    assert login(client, id_number="00000000", password="first-pass1").status_code == 200

    monkeypatch.setattr(settings, "admin_name", "New Name")
    monkeypatch.setattr(settings, "admin_email", "New@B.com")
    monkeypatch.setattr(settings, "admin_password", "second-pass2")
    auth_service.ensure_admin(db)
    assert login(client, id_number="00000000", password="first-pass1").status_code == 401
    token = login(client, id_number="00000000", password="second-pass2").json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["role"] == "coordinator"
    assert me["full_name"] == "New Name"


def test_ensure_admin_changing_id_and_email_keeps_one_admin(client, db, monkeypatch):
    monkeypatch.setattr(settings, "admin_email", "a@b.com")
    monkeypatch.setattr(settings, "admin_id_number", "00000000")
    monkeypatch.setattr(settings, "admin_password", "first-pass1")
    first = auth_service.ensure_admin(db)

    monkeypatch.setattr(settings, "admin_id_number", "11111111")
    assert auth_service.ensure_admin(db).id == first.id
    monkeypatch.setattr(settings, "admin_email", "c@d.com")
    monkeypatch.setattr(settings, "admin_id_number", "22222222")
    assert auth_service.ensure_admin(db).id == first.id

    coordinators = db.scalars(select(User).where(User.role == Role.coordinator)).all()
    assert [(u.id_number, u.email) for u in coordinators] == [("22222222", "c@d.com")]
    assert login(client, id_number="00000000", password="first-pass1").status_code == 401
    assert login(client, id_number="22222222", password="first-pass1").status_code == 200


def test_cannot_reregister_within_48_hours(client, db):
    body = {"email": "s@g.bracu.ac.bd", "id_number": "22222222", "full_name": "S", "password": "Password123", "role": "student"}
    old_id = client.post("/api/auth/register", json=body).json()["id"]
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 409
    assert r.json()["detail"] == REGISTER_TAKEN

    # 48 hours pass without a decision: a new submission replaces the old one.
    user = db.get(User, old_id)
    user.created_at -= timedelta(hours=48, minutes=1)
    db.commit()
    r = client.post("/api/auth/register", json=body)
    assert r.status_code == 201
    assert r.json()["id"] != old_id and db.get(User, old_id) is None


def test_register_rejects_bad_email_and_weak_password(client):
    r = register(client, email="no-at-sign")
    assert r.status_code == 422
    assert r.json()["detail"].startswith("email:")
    for bad_id in ["1234567", "123456789", "12a45678", "１２３４５６７８"]:
        r = register(client, id_number=bad_id)
        assert r.status_code == 422, bad_id
        assert r.json()["detail"].startswith("id_number:"), bad_id
    for weak in ["Short1", "alllower123", "ALLUPPER123", "NoDigitsHere", "Has Space1"]:
        r = register(client, password=weak)
        assert r.status_code == 422, weak
        assert r.json()["detail"].startswith("password:"), weak


def test_account_deletion_needs_a_reason_approval_and_7_days(client, db, tmp_path, timelines):
    student, sup = supervised_student(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert upload(client, student).status_code == 201
    pdfs = list(tmp_path.rglob("*.pdf"))
    assert len(pdfs) == 1

    assert client.post("/api/auth/me/deletion-request", headers=coord, json=REASON).status_code == 403
    assert client.post("/api/auth/me/deletion-request", headers=student).status_code == 422  # no reason
    r = client.post("/api/auth/me/deletion-request", headers=student, json={"reason": "  bye  "})
    assert r.status_code == 422 and r.json()["detail"].startswith("reason:")  # one word isn't a reason
    r = client.post("/api/auth/me/deletion-request", headers=student, json=REASON)
    me = r.json()
    assert r.status_code == 200 and me["deletion_pending"] is True and me["deletion_by_coordinator"] is False
    assert me["coordinator_contact"] is None  # their own request: no "contact the coordinator" message
    assert me["deletion_reason"] == REASON["reason"] and me["deletion_executes_at"] is None  # no clock until approved
    assert client.post("/api/auth/me/deletion-request", headers=student, json=REASON).status_code == 409

    assert client.get("/api/auth/deletion-requests", headers=student).status_code == 403
    pending = client.get("/api/auth/deletion-requests", headers=coord).json()
    assert [(p["email"], p["deletion_reason"]) for p in pending] == [("s@b.com", REASON["reason"])]
    uid = pending[0]["id"]
    assert client.get("/api/auth/me/counts", headers=coord).json()["deletion_requests"] == 1
    assert run_deletions_due(db) == (0, 0)  # 7 days alone do nothing without approval
    assert client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=student).status_code == 403
    approved = client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord)
    assert approved.status_code == 200 and approved.json()["deletion_executes_at"] is not None
    assert client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord).status_code == 404  # once
    assert client.get("/api/auth/me/counts", headers=coord).json()["deletion_requests"] == 0  # decided
    assert account_service.run_due_deletions(db) == 0  # approved, but the 7 days aren't over
    assert client.get("/api/auth/me", headers=student).status_code == 200  # still usable while waiting

    assert run_deletions_due(db) == (1, 0)
    assert db.get(User, uid) is None
    assert pdfs[0].exists()  # the thesis and its versions are kept as an archive
    assert client.get("/api/auth/me", headers=student).status_code == 401
    theses = client.get("/api/theses", headers=sup).json()
    assert [(t["status"], t["student"], len(t["versions"])) for t in theses] == [("dropped", None, 1)]


def test_only_the_coordinator_cancels_a_deletion(client, db):
    student = auth(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    uid = client.post("/api/auth/me/deletion-request", headers=student, json=REASON).json()["id"]
    assert client.delete(f"/api/auth/deletion-requests/{uid}", headers=student).status_code == 403
    client.post(f"/api/auth/deletion-requests/{uid}/approve", headers=coord)
    assert client.delete(f"/api/auth/deletion-requests/{uid}", headers=student).status_code == 403  # approved: still only them
    r = client.delete(f"/api/auth/deletion-requests/{uid}", headers=coord)
    assert r.status_code == 200 and (r.json()["deletion_pending"], r.json()["deletion_reason"]) == (False, None)
    assert client.get("/api/auth/deletion-requests", headers=coord).json() == []
    assert client.delete(f"/api/auth/deletion-requests/{uid}", headers=coord).status_code == 404
    assert run_deletions_due(db) == (0, 0) and db.get(User, uid) is not None
    # The user may ask again.
    assert client.post("/api/auth/me/deletion-request", headers=student, json=REASON).status_code == 200


def test_coordinator_lists_and_schedules_account_deletions(client, db, tmp_path, timelines):
    student = make_student(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert upload(client, student).status_code == 201
    assert register(client).status_code == 201  # unapproved sign-up: not an account yet

    assert client.get("/api/auth/accounts", headers=student).status_code == 403
    accounts = client.get("/api/auth/accounts", headers=coord).json()
    by_email = {a["email"]: a["id"] for a in accounts}
    supervisor_email = next(e for e in by_email if e.startswith("sup"))
    assert set(by_email) == {"s@b.com", supervisor_email}  # coordinator is the admin login, not listed
    student_id = db.scalar(select(User.id_number).where(User.email == "s@b.com"))
    emails = lambda q: [a["email"] for a in client.get(f"/api/auth/accounts?{q}", headers=coord).json()]
    assert emails(f"role=student&id_prefix={student_id[:3]}") == ["s@b.com"]
    assert emails("role=faculty") == [supervisor_email]
    assert emails("id_prefix=%25") == []  # LIKE wildcards are matched literally
    assert client.get("/api/auth/accounts?role=coordinator", headers=coord).status_code == 422

    schedule = lambda uid, headers=coord, body=REASON: client.post(f"/api/auth/accounts/{uid}/deletion", headers=headers, json=body)
    coord_id = db.scalar(select(User.id).where(User.email == "coord@b.com"))
    assert schedule(by_email["s@b.com"], headers=student).status_code == 403
    assert schedule(coord_id).status_code == 403
    assert schedule(by_email["s@b.com"], body={}).status_code == 422  # the coordinator gives a reason too
    # A supervisor of an active thesis is kept; once the thesis is archived they can go.
    assert schedule(by_email[supervisor_email]).status_code == 409
    r = schedule(by_email["s@b.com"])
    assert r.status_code == 200 and r.json()["deletion_by_coordinator"] is True
    # The owner sees it on their next page load: the date, the reason and who to contact before it runs.
    mine = client.get("/api/auth/me", headers=student).json()
    assert (mine["deletion_reason"], mine["coordinator_contact"]) == (REASON["reason"], settings.admin_email)
    assert mine["deletion_executes_at"] is not None
    assert schedule(by_email["s@b.com"]).status_code == 409  # already scheduled
    assert db.get(User, by_email["s@b.com"]) is not None  # nothing happens before the 7 days
    assert run_deletions_due(db) == (1, 0)
    assert db.get(User, by_email["s@b.com"]) is None
    assert len(list(tmp_path.rglob("*.pdf"))) == 1  # versions are never lost
    assert schedule(by_email[supervisor_email]).status_code == 200
    assert schedule(by_email["s@b.com"]).status_code == 404


def test_pending_counts_and_name_fields(client, db):
    student = auth(client, db, "s@b.com")
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert register(client).status_code == 201
    assert client.post("/api/auth/me/deletion-request", headers=student, json=REASON).status_code == 200

    assert client.get("/api/auth/me/counts", headers=student).json() == {}
    assert client.get("/api/auth/me/counts", headers=coord).json() == {
        "registration_requests": 1,
        "deletion_requests": 1,
        "restart_requests": 0,
    }

    user = User(full_name="ada byron king")
    assert (user.first_name, user.monogram) == ("ada", "AB")


def test_login_is_rate_limited_per_account(client):
    codes = [login(client, password="Wrong1234").status_code for _ in range(rate_limit.LOGIN_PER_ACCOUNT + 1)]
    assert set(codes[:-1]) == {401}
    assert codes[-1] == 429
    # Another account from the same IP is not locked out.
    assert login(client, id_number="87654321", password="Wrong1234").status_code == 401


def test_failed_logins_from_one_ip_do_not_lock_out_the_owner(client, db):
    register(client)
    db.scalar(select(User).where(User.id_number == "12345678")).approved = True
    db.flush()
    for _ in range(rate_limit.LOGIN_PER_ACCOUNT):
        with pytest.raises(HTTPException) as exc:
            auth_service.login(db, "12345678", "Wrong1234", ip="10.0.0.9")
        assert exc.value.status_code == 401
    with pytest.raises(HTTPException) as exc:
        auth_service.login(db, "12345678", "Wrong1234", ip="10.0.0.9")
    assert exc.value.status_code == 429
    # The owner, from another IP, still gets in; right logins don't use up the budget.
    assert all(login(client).status_code == 200 for _ in range(rate_limit.LOGIN_PER_ACCOUNT + 1))


def test_guessing_from_many_ips_does_not_lock_out_a_known_ip(client, db, monkeypatch):
    monkeypatch.setattr(rate_limit, "LOGIN_PER_ACCOUNT_ALL_IPS", 3)
    register(client)
    db.scalar(select(User).where(User.id_number == "12345678")).approved = True
    db.flush()
    assert login(client).status_code == 200  # the owner's usual IP is now known
    for i in range(3):
        with pytest.raises(HTTPException):
            auth_service.login(db, "12345678", "Wrong1234", ip=f"10.0.0.{i}")
    with pytest.raises(HTTPException) as exc:
        auth_service.login(db, "12345678", "Wrong1234", ip="10.0.0.99")
    assert exc.value.status_code == 429  # new IPs hit the account-wide cap
    assert login(client).status_code == 200


def test_login_is_rate_limited_per_ip(client):
    body = {"email": "nobody@example.com", "password": "wrong"}
    codes = [client.post("/api/auth/login", json=body).status_code for _ in range(rate_limit.LIMITS["/api/auth/login"] + 1)]
    assert 429 not in codes[:-1]
    assert codes[-1] == 429


def test_signed_in_users_get_their_own_bucket(client, db, monkeypatch):
    a, b = auth(client, db, "a@b.com"), auth(client, db, "b@b.com")
    monkeypatch.setitem(rate_limit.LIMITS, "/api/", 2)
    assert [client.get("/api/auth/me", headers=a).status_code for _ in range(3)] == [200, 200, 429]
    assert client.get("/api/auth/me", headers=b).status_code == 200


def test_password_change_logs_out_old_tokens(client, db):
    headers = auth(client, db, "a@b.com")
    user = db.scalar(select(User).where(User.email == "a@b.com"))
    user.password_hash = hash_password("NewPassword1")
    db.flush()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_overlong_login_password_is_refused(client):
    register(client)
    assert login(client, password="A" * 10_000).status_code == 401


def test_chunked_body_is_refused_before_auth(client):
    def body():
        yield b"x" * 1024

    assert client.post("/api/proposals/mine/versions", content=body()).status_code == 411


def test_login_still_works_and_is_limited_when_redis_is_down(client, monkeypatch):
    # Nothing listens on port 1, so every Redis call fails at once.
    monkeypatch.setattr(rate_limit, "redis", Redis.from_url("redis://localhost:1", socket_connect_timeout=0.5))
    assert register(client).status_code < 300  # requests go through instead of failing on Redis
    codes = [login(client, password="Wrong1234").status_code for _ in range(rate_limit.LOGIN_PER_ACCOUNT + 1)]
    assert codes == [401] * rate_limit.LOGIN_PER_ACCOUNT + [429]  # memory fallback still limits guessing


def test_guesses_during_a_redis_outage_still_count_after_it(client, monkeypatch):
    real = rate_limit.redis
    monkeypatch.setattr(rate_limit, "redis", Redis.from_url("redis://localhost:1", socket_connect_timeout=0.5))
    register(client)
    assert {login(client, password="Wrong1234").status_code for _ in range(rate_limit.LOGIN_PER_ACCOUNT)} == {401}
    monkeypatch.setattr(rate_limit, "redis", real)
    monkeypatch.setattr(rate_limit, "_redis_down_until", 0.0)  # Redis is back
    assert login(client, password="Wrong1234").status_code == 429


def test_counts_from_other_processes_come_from_redis(client):
    register(client)
    assert {login(client, password="Wrong1234").status_code for _ in range(rate_limit.LOGIN_PER_ACCOUNT)} == {401}
    rate_limit._hits.clear()  # as if the next login reached a different backend process
    assert login(client, password="Wrong1234").status_code == 429


def test_database_outage_is_a_clear_503(client):
    def down():
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    app.dependency_overrides[get_db] = down
    res = login(client)
    assert (res.status_code, res.headers["retry-after"]) == (503, "5")
    assert "database" in res.json()["detail"]


@pytest.mark.parametrize("body", [{"full_name": "a\x00b"}, {"id_number": "1234\x00"}])
def test_nul_characters_are_a_422_not_a_500(client, body):
    if "full_name" in body:
        res = client.post("/api/auth/register", json={**body, "email": "n@g.bracu.ac.bd", "id_number": "12345670", "password": "Password123"})
    else:
        res = client.post("/api/auth/login", data={"username": body["id_number"], "password": "x"})
    assert res.status_code == 422, res.text


def test_id_past_integer_range_is_a_422(client, db):
    h = auth(client, db, "c@b.com", Role.coordinator)
    assert client.delete(f"/api/auth/deletion-requests/{2**40}", headers=h).status_code == 422


def test_big_bodies_need_a_signed_in_user(client):
    res = client.post("/api/proposals/mine/versions", content=b"x" * (70 * 1024), headers={"content-type": "application/pdf"})
    assert res.status_code == 401
    forged = client.post(
        "/api/proposals/mine/versions", content=b"x" * (70 * 1024), headers={"authorization": "Bearer nope"}
    )
    assert forged.status_code == 401


def test_responses_carry_security_headers(client):
    res = client.get("/api/auth/me")
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in res.headers["content-security-policy"]


@pytest.mark.parametrize("password", ["short1A", "alllowercase1", "NoDigitsHere", "Has Space1"])
def test_weak_admin_password_refuses_to_start(password):
    with pytest.raises(ValueError):
        type(settings)(admin_password=password)


def test_logout_ends_every_session_of_that_person(client, db):
    laptop = auth(client, db, "l@b.com")
    me_id = client.get("/api/auth/me", headers=laptop).json()["id_number"]
    phone = {"Authorization": f"Bearer {login(client, me_id, 'Password123').json()['access_token']}"}
    other = auth(client, db, "o@b.com")
    assert client.post("/api/auth/logout", headers=laptop).status_code == 204
    assert client.get("/api/auth/me", headers=laptop).status_code == 401
    assert client.get("/api/auth/me", headers=phone).status_code == 401  # a copied token dies too
    assert client.get("/api/auth/me", headers=other).status_code == 200  # other people stay signed in
    fresh = {"Authorization": f"Bearer {login(client, me_id, 'Password123').json()['access_token']}"}
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_logged_out_token_cannot_start_a_big_upload(client, db):
    h = auth(client, db, "s@b.com")
    assert client.post("/api/auth/logout", headers=h).status_code == 204
    res = client.post("/api/proposals/mine/versions", content=b"x" * (70 * 1024), headers=h)
    assert (res.status_code, res.json()["detail"]) == (401, "Sign in to upload")


def test_login_tells_an_applicant_their_request_status(client, db):
    body = {"email": "s@g.bracu.ac.bd", "id_number": "22222222", "full_name": "S", "password": "Password123", "role": "student"}
    uid = client.post("/api/auth/register", json=body).json()["id"]
    res = client.post("/api/auth/login", data={"username": "22222222", "password": "Password123"})
    assert res.status_code == 403 and "waiting for coordinator approval" in res.json()["detail"]
    db.get(User, uid).created_at -= timedelta(hours=48, minutes=1)
    db.flush()
    res = client.post("/api/auth/login", data={"username": "22222222", "password": "Password123"})
    assert (res.status_code, res.json()["detail"]) == (403, "Your registration request expired without a decision. Register again")
    # Without the password nobody learns anything.
    assert client.post("/api/auth/login", data={"username": "22222222", "password": "Wrong1234"}).status_code == 401


def test_an_expired_registration_request_cannot_be_approved(client, db):
    uid = register(client).json()["id"]
    db.get(User, uid).created_at -= timedelta(hours=48, minutes=1)
    db.commit()
    coord = auth(client, db, "coord@b.com", Role.coordinator)
    assert client.get("/api/auth/registration-requests", headers=coord).json() == []
    assert client.get("/api/auth/me/counts", headers=coord).json()["registration_requests"] == 0
    assert client.post(f"/api/auth/registration-requests/{uid}/approve", headers=coord).status_code == 404
    assert login(client).status_code == 403


def test_deletion_request_for_a_vanished_account_is_a_401(client, db):
    h = auth(client, db, "gone@b.com")
    db.delete(db.get(User, me_id := client.get("/api/auth/me", headers=h).json()["id"]))
    db.flush()
    with pytest.raises(HTTPException) as exc:
        account_service.request_deletion(db, User(id=me_id), REASON["reason"])
    assert exc.value.status_code == 401
