import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.milestone import Milestone, Phase

# Tests use a separate database so they never touch dev data.
TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def tables():
    # Build the schema once per run, not once per test.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(tables):
    # Each test runs inside one transaction that is rolled back at the end.
    # Commits in services become savepoints, so nothing leaks between tests.
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, autoflush=False, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    # Uploads go to a per-test temp dir, never the dev uploads folder.
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def timelines(db):
    # Uploads need the phase's timeline set; tests that aren't about timelines get all of them.
    due = datetime.now(timezone.utc) + timedelta(days=30)
    db.add_all(Milestone(phase=p, due_at=due, grace_days=0, penalty_per_day=0) for p in Phase)
    db.flush()
