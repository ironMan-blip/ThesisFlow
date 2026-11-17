import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.config import settings
from app.database import Base, get_db
from app import rate_limit, virus_scan
from app.main import app
from app.models.milestone import MilestoneTemplate, Phase
from app.models.semester import Semester
from app.services.progress_service import current_semester_id

# Tests use a separate database so they never touch dev data.
TEST_DATABASE_URL = os.environ["TEST_DATABASE_URL"]
engine = create_engine(TEST_DATABASE_URL)
# Likewise a separate Redis database, since every test wipes it.
rate_limit.redis = Redis.from_url(os.environ["TEST_REDIS_URL"], decode_responses=True)


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


@pytest.fixture(autouse=True)
def no_virus_scanner(monkeypatch):
    # clamd is an outside service: tests treat every file as clean, except tests/test_virus_scan.py, which uses it.
    monkeypatch.setattr(virus_scan, "scan", lambda path: None)


@pytest.fixture(autouse=True)
def fresh_rate_limit():
    # Every test shares the "testclient" IP; start each with empty buckets.
    rate_limit.reset()


@pytest.fixture(autouse=True)
def semester(db):
    # The migration creates the first semester; tests start inside its P1 registration week.
    row = Semester(started_at=datetime.now(timezone.utc))
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def timelines(db):
    # Uploads need the phase's timeline set; tests that aren't about timelines get all of them.
    due = datetime.now(timezone.utc) + timedelta(days=30)
    db.add_all(MilestoneTemplate(semester_id=current_semester_id(db), phase=p, due_at=due, grace_days=0, penalty_per_day=0) for p in Phase)
    db.flush()
