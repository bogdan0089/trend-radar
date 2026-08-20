import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

FIXTURES_DIR = Path(__file__).parent / "fixtures"

TEST_DB_NAME = "trend_radar_test"
DEFAULT_HOST_URL = "postgresql+psycopg://trend:trend@localhost:5442"
HOST_URL = os.getenv("TEST_DATABASE_HOST_URL", DEFAULT_HOST_URL)
TEST_DATABASE_URL = f"{HOST_URL}/{TEST_DB_NAME}"

REQUIRE_DB = os.getenv("REQUIRE_TEST_DB", "").lower() in ("1", "true", "yes")


@pytest.fixture(scope="session")
def load_fixture():
    """Read an HTML fixture by file name."""

    def _load(name: str) -> str:
        return (FIXTURES_DIR / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(scope="session")
def bestsellers_html(load_fixture) -> str:
    return load_fixture("amazon_bestsellers.html")


@pytest.fixture(scope="session")
def blocked_html(load_fixture) -> str:
    return load_fixture("amazon_blocked.html")


def _create_database_if_missing() -> None:
    """Create the test database, connecting through the maintenance database."""
    admin = create_engine(f"{HOST_URL}/postgres", isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine():
    """Engine against a dedicated test database, or skip if Postgres is down."""
    try:
        _create_database_if_missing()
        engine = create_engine(TEST_DATABASE_URL)
        with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 — any connection problem means skip
        message = f"Postgres unavailable at {HOST_URL}: {exc}"
        if REQUIRE_DB:
            pytest.fail(f"REQUIRE_TEST_DB is set but {message}", pytrace=False)
        pytest.skip(message)

    import app.models  # noqa: F401 — registers every table on the metadata
    from app.db.base import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """A session rolled back after each test."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """TestClient wired to the rolled-back session."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db_session):
    """The seeded admin, created the same way startup does."""
    from app.services.auth_service import AuthService

    AuthService(db_session).ensure_admin("admin", "admin123")
    return {"username": "admin", "password": "admin123"}


@pytest.fixture
def auth_headers(client, admin_user):
    response = client.post("/api/auth/login", json=admin_user)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
