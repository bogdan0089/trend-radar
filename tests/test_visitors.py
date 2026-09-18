"""Self-registered visitors: what they may do next to the admin."""

import io

import pytest

from app.models.scrape_run import ScrapeRun


def register(client, username="visitor1", password="visitor-pass"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


@pytest.fixture
def visitor_headers(client):
    response = register(client)
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def queued_runs(monkeypatch):
    """Record pipeline runs instead of sending them to Celery."""
    import app.celery.tasks.pipeline as tasks

    class FakeAsyncResult:
        id = "fake-task-id"

    monkeypatch.setattr(tasks.run_pipeline, "delay", lambda **kw: FakeAsyncResult())


def finish_all_runs(db_session) -> None:
    db_session.query(ScrapeRun).update({"status": "success"})
    db_session.flush()


class TestRegistration:
    def test_sign_up_returns_a_working_token(self, client):
        response = register(client)

        assert response.status_code == 201
        token = response.json()["access_token"]
        me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.json()["username"] == "visitor1"
        assert me.json()["is_admin"] is False

    def test_an_email_is_a_valid_username(self, client):
        response = register(client, username="jane.doe+radar@example.com")

        assert response.status_code == 201

    def test_a_taken_username_is_a_409(self, client):
        register(client)

        assert register(client).status_code == 409

    def test_the_admin_username_cannot_be_registered(self, client, admin_user):
        assert register(client, username=admin_user["username"]).status_code == 409

    @pytest.mark.parametrize(
        "username, password",
        [
            ("ab", "long-enough"),
            ("has space", "long-enough"),
            ("visitor", "short"),
        ],
    )
    def test_invalid_sign_ups_are_rejected(self, client, username, password):
        assert register(client, username, password).status_code == 422

    def test_the_admin_is_reported_as_admin(self, client, auth_headers):
        assert client.get("/api/auth/me", headers=auth_headers).json()["is_admin"] is True


class TestVisitorPermissions:
    def test_a_visitor_reads_the_dashboard(self, client, visitor_headers):
        assert client.get("/api/products", headers=visitor_headers).status_code == 200
        assert client.get("/api/sales-boost", headers=visitor_headers).status_code == 200

    def test_a_visitor_cannot_add_to_the_sales_history(self, client, visitor_headers):
        response = client.post(
            "/api/sales-boost",
            headers=visitor_headers,
            json={"title": "Something", "category": "Electronics"},
        )

        assert response.status_code == 403

    def test_a_visitor_cannot_import_a_csv(self, client, visitor_headers):
        upload = {"file": ("past.csv", io.BytesIO(b"title,category\nA,B\n"), "text/csv")}

        response = client.post(
            "/api/sales-boost/import-csv", headers=visitor_headers, files=upload
        )

        assert response.status_code == 403


class TestRunCooldown:
    def test_a_visitor_can_start_a_run(self, client, visitor_headers, queued_runs):
        assert client.post("/api/scrape-runs", headers=visitor_headers).status_code == 202

    def test_a_visitor_waits_out_the_cooldown(
        self, client, visitor_headers, queued_runs, db_session
    ):
        client.post("/api/scrape-runs", headers=visitor_headers)
        finish_all_runs(db_session)

        response = client.post("/api/scrape-runs", headers=visitor_headers)

        assert response.status_code == 429
        assert "Try again in" in response.json()["detail"]

    def test_the_cooldown_counts_runs_started_by_anyone(
        self, client, visitor_headers, auth_headers, queued_runs, db_session
    ):
        """Otherwise a second account would be a way around it."""
        client.post("/api/scrape-runs", headers=auth_headers)
        finish_all_runs(db_session)

        assert client.post("/api/scrape-runs", headers=visitor_headers).status_code == 429

    def test_the_admin_is_not_limited(self, client, auth_headers, queued_runs, db_session):
        client.post("/api/scrape-runs", headers=auth_headers)
        finish_all_runs(db_session)

        assert client.post("/api/scrape-runs", headers=auth_headers).status_code == 202
