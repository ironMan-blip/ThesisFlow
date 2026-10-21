import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.database import Base, get_db
from app.main import app

# Tests use a separate database so they never touch dev data.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://thesisflow:thesisflow@localhost:5432/thesisflow_test"
)
engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session")
def tables():
    # Build the schema once per run, not once per test.
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
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


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
