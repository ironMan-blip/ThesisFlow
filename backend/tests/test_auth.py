def register(client, email="a@b.com", password="password123"):
    return client.post("/api/auth/register", json={"email": email, "full_name": "A", "password": password})


def login(client, email="a@b.com", password="password123"):
    return client.post("/api/auth/login", data={"username": email, "password": password})


def test_register_login_me(client):
    assert register(client).status_code == 201
    token = login(client).json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "student"


def test_duplicate_email_rejected(client):
    register(client)
    assert register(client, email="A@B.com").status_code == 409


def test_wrong_password_rejected(client):
    register(client)
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401
