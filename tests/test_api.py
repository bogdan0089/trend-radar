"""API tests against a real Postgres."""

import io

import pytest

from app.core.config import settings

PROTECTED_ENDPOINTS = [
    ("get", "/api/products"),
    ("get", "/api/sales-boost"),
    ("post", "/api/sales-boost"),
    ("get", "/api/scrape-runs"),
    ("get", "/api/scrape-runs/latest"),
    ("post", "/api/scrape-runs"),
    ("get", "/api/auth/me"),
]


def csv_upload(text: str, name: str = "past.csv"):
    return {"file": (name, io.BytesIO(text.encode("utf-8")), "text/csv")}


class TestHealth:
    def test_health_is_public(self, client):
        """Health must answer without a token, or orchestration cannot probe it."""
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_reports_the_no_key_mode(self, client, monkeypatch):
        """The spec requires running with no key; health has to show that state."""
        monkeypatch.setattr(settings, "llm_provider", "none")
        monkeypatch.setattr(settings, "llm_api_key", "")

        body = client.get("/api/health").json()

        assert body["llm_enabled"] is False
        assert body["llm_provider"] == "none"

    def test_health_reports_a_configured_provider(self, client, monkeypatch):
        monkeypatch.setattr(settings, "llm_provider", "gemini")
        monkeypatch.setattr(settings, "llm_api_key", "test-key")

        body = client.get("/api/health").json()

        assert body["llm_enabled"] is True
        assert body["llm_provider"] == "gemini"


class TestLogin:
    def test_valid_credentials_return_a_token(self, client, admin_user):
        response = client.post("/api/auth/login", json=admin_user)

        assert response.status_code == 200
        assert response.json()["token_type"] == "bearer"
        assert response.json()["access_token"]

    def test_wrong_password_is_rejected(self, client, admin_user):
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "nope"}
        )

        assert response.status_code == 401

    def test_unknown_user_gives_the_same_error_as_a_wrong_password(self, client, admin_user):
        """Otherwise the form would reveal which usernames exist."""
        unknown = client.post(
            "/api/auth/login", json={"username": "ghost", "password": "nope"}
        )
        wrong = client.post(
            "/api/auth/login", json={"username": "admin", "password": "nope"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json()["detail"] == wrong.json()["detail"]

    def test_me_returns_the_current_user(self, client, auth_headers):
        response = client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        assert response.json()["username"] == "admin"
        assert response.json()["is_active"] is True


class TestAuthorizationWall:
    """"Restricted access to the panel" from the spec, checked per endpoint."""

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
    def test_no_token_is_rejected(self, client, method, path):
        assert getattr(client, method)(path).status_code == 401

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
    def test_malformed_token_is_rejected(self, client, method, path):
        headers = {"Authorization": "Bearer not-a-real-token"}
        assert getattr(client, method)(path, headers=headers).status_code == 401

    def test_token_of_a_deleted_user_is_rejected(self, client, auth_headers, db_session):
        """A valid signature is not enough once the user is gone."""
        from app.repositories.user import UserRepository

        users = UserRepository(db_session)
        users.delete(users.get_by_username("admin"))
        db_session.commit()

        assert client.get("/api/products", headers=auth_headers).status_code == 401

    def test_a_rejection_names_the_scheme(self, client):
        """RFC 9110: a 401 must say which scheme to authenticate with.

        The dependency raises a domain error now instead of building its own
        HTTPException, so the header has to come from the exception handler.
        """
        response = client.get("/api/products")

        assert response.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize(("method", "path"), PROTECTED_ENDPOINTS)
    def test_every_rejection_reads_the_same(self, client, method, path):
        """No token, a broken token and a deleted user answer identically, so
        the response cannot be used to probe which part failed."""
        no_token = getattr(client, method)(path)
        broken = getattr(client, method)(path, headers={"Authorization": "Bearer nope"})

        assert no_token.json()["detail"] == broken.json()["detail"]


class TestProducts:
    def test_empty_list_has_the_pagination_envelope(self, client, auth_headers):
        body = client.get("/api/products", headers=auth_headers).json()

        assert body == {"items": [], "total": 0, "limit": 50, "offset": 0}

    def test_product_without_a_score_is_still_listed(self, client, auth_headers, db_session):
        """A freshly scraped product has no score yet and must still be listed."""
        from app.repositories.product import ProductRepository

        ProductRepository(db_session).upsert_many(
            [
                {
                    "asin": "B00TEST001",
                    "title": "Test Product",
                    "category": "Electronics",
                    "price": None,
                    "currency": "USD",
                    "rating": None,
                    "reviews_count": 0,
                    "product_url": "https://www.amazon.com/dp/B00TEST001",
                    "image_url": None,
                    "source": "test",
                }
            ]
        )
        db_session.commit()

        body = client.get("/api/products", headers=auth_headers).json()

        assert body["total"] == 1
        assert body["items"][0]["asin"] == "B00TEST001"
        assert body["items"][0]["score"] is None
        assert body["items"][0]["trend_delta_pct"] is None

    def test_limit_is_validated(self, client, auth_headers):
        assert client.get("/api/products?limit=0", headers=auth_headers).status_code == 422
        assert client.get("/api/products?limit=999", headers=auth_headers).status_code == 422


class TestPastProductsForm:
    def test_manual_entry_is_stored(self, client, auth_headers):
        response = client.post(
            "/api/sales-boost",
            headers=auth_headers,
            json={
                "title": "Yoga Mat Pro",
                "category": "Sports",
                "keywords": ["Yoga", "yoga", " MAT "],
                "notes": "sold well in spring",
            },
        )

        assert response.status_code == 201
        body = response.json()
        assert body["source"] == "manual"
        assert body["keywords"] == ["yoga", "mat"]

    def test_keywords_are_derived_from_the_title_when_omitted(self, client, auth_headers):
        """An entry without keywords still has to be matchable."""
        response = client.post(
            "/api/sales-boost",
            headers=auth_headers,
            json={"title": "Ninja Air Fryer Basket", "category": "Kitchen"},
        )

        assert response.status_code == 201
        assert "fryer" in response.json()["keywords"]

    @pytest.mark.parametrize(
        "payload",
        [
            {"title": "", "category": "Sports"},
            {"title": "   ", "category": "Sports"},
            {"title": "Valid", "category": ""},
            {"category": "Sports"},
        ],
    )
    def test_invalid_payloads_are_rejected(self, client, auth_headers, payload):
        response = client.post("/api/sales-boost", headers=auth_headers, json=payload)

        assert response.status_code == 422

    def test_created_entry_appears_in_the_list(self, client, auth_headers):
        client.post(
            "/api/sales-boost",
            headers=auth_headers,
            json={"title": "Air Fryer", "category": "Kitchen"},
        )

        body = client.get("/api/sales-boost", headers=auth_headers).json()

        assert body["total"] == 1
        assert body["items"][0]["title"] == "Air Fryer"


class TestPastProductsCsvImport:
    def test_valid_file_is_imported(self, client, auth_headers):
        csv_text = (
            "title,category,keywords,notes\n"
            "Yoga Mat,Sports,yoga;mat,spring hit\n"
            "Air Fryer,Kitchen,fryer;kitchen,\n"
        )

        response = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=csv_upload(csv_text)
        )

        assert response.status_code == 200
        assert response.json() == {"imported": 2, "skipped": 0, "errors": []}

    def test_alternative_column_names_are_accepted(self, client, auth_headers):
        """A file using 'name'/'niche' should not be rejected outright."""
        csv_text = "name,niche\nYoga Mat,Sports\n"

        body = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=csv_upload(csv_text)
        ).json()

        assert body["imported"] == 1

    def test_broken_rows_do_not_fail_the_whole_file(self, client, auth_headers):
        """Partial success is a normal import outcome, not a failed request."""
        csv_text = (
            "title,category\n"
            "Yoga Mat,Sports\n"
            ",Sports\n"
            "No Category,\n"
            "Air Fryer,Kitchen\n"
        )

        response = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=csv_upload(csv_text)
        )

        assert response.status_code == 200
        body = response.json()
        assert body["imported"] == 2
        assert body["skipped"] == 2
        assert len(body["errors"]) == 2

    def test_reimporting_the_same_file_adds_nothing(self, client, auth_headers):
        csv_text = "title,category\nYoga Mat,Sports\n"
        files_first = csv_upload(csv_text)
        files_second = csv_upload(csv_text)

        client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=files_first
        )
        body = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=files_second
        ).json()

        assert body["imported"] == 0
        assert body["skipped"] == 1
        assert "duplicate" in body["errors"][0]

    def test_missing_required_columns_are_reported(self, client, auth_headers):
        response = client.post(
            "/api/sales-boost/import-csv",
            headers=auth_headers,
            files=csv_upload("foo,bar\n1,2\n"),
        )

        assert response.status_code == 422
        assert "title" in response.json()["detail"]

    def test_empty_file_is_rejected(self, client, auth_headers):
        response = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=csv_upload("")
        )

        assert response.status_code == 422

    def test_an_oversized_cell_is_a_422_not_a_crash(self, client, auth_headers):
        """A cell past the csv module's 128 KB field limit raises csv.Error,
        which is neither a ValueError nor a DomainError. It used to leave the
        endpoint as a 500 on a file the user could actually fix, and the whole
        upload is well under the 5 MB cap."""
        oversized = "x" * 200_000
        response = client.post(
            "/api/sales-boost/import-csv",
            headers=auth_headers,
            files=csv_upload(f'title,category\r\n"{oversized}",Electronics\r\n'),
        )

        assert response.status_code == 422
        assert "CSV" in response.json()["detail"]

    def test_an_unterminated_quote_is_a_422_not_a_crash(self, client, auth_headers):
        response = client.post(
            "/api/sales-boost/import-csv",
            headers=auth_headers,
            files=csv_upload('title,category\r\n"Yoga Mat,Sports\r\n'),
        )

        assert response.status_code in (200, 422)
        assert response.status_code != 500

    def test_excel_bom_does_not_break_the_header(self, client, auth_headers):
        """Excel prepends a BOM, which would otherwise hide the title column."""
        files = {
            "file": (
                "past.csv",
                io.BytesIO("title,category\nYoga Mat,Sports\n".encode("utf-8-sig")),
                "text/csv",
            )
        }

        body = client.post(
            "/api/sales-boost/import-csv", headers=auth_headers, files=files
        ).json()

        assert body["imported"] == 1


class TestRuns:
    def test_latest_is_null_before_any_run(self, client, auth_headers):
        response = client.get("/api/scrape-runs/latest", headers=auth_headers)

        assert response.status_code == 200
        assert response.json() is None

    def test_history_is_empty_before_any_run(self, client, auth_headers):
        assert client.get("/api/scrape-runs", headers=auth_headers).json() == {"items": []}

    def test_history_returns_runs_newest_first(self, client, auth_headers, db_session):
        from app.repositories.scrape_run import ScrapeRunRepository

        runs = ScrapeRunRepository(db_session)
        runs.create_pending(trigger="manual")
        runs.create_pending(trigger="schedule")
        db_session.commit()

        items = client.get("/api/scrape-runs", headers=auth_headers).json()["items"]

        assert [item["trigger"] for item in items] == ["schedule", "manual"]

    def test_start_run_returns_202_without_blocking(self, client, auth_headers, monkeypatch):
        """The heavy work must be queued, never executed inside the request."""
        import app.celery.tasks.pipeline as tasks

        class FakeAsyncResult:
            id = "fake-task-id"

        calls = []

        def fake_delay(**kwargs):
            calls.append(kwargs)
            return FakeAsyncResult()

        monkeypatch.setattr(tasks.run_pipeline, "delay", fake_delay)

        response = client.post("/api/scrape-runs", headers=auth_headers)

        assert response.status_code == 202
        assert response.json()["status"] == "pending"
        assert response.json()["trigger"] == "manual"
        assert calls == [{"run_id": response.json()["id"], "trigger": "manual"}]

    def test_second_run_reuses_the_active_one(self, client, auth_headers, monkeypatch):
        """Two concurrent scrapes would double the load and race on the same ASINs."""
        import app.celery.tasks.pipeline as tasks

        class FakeAsyncResult:
            id = "fake-task-id"

        monkeypatch.setattr(tasks.run_pipeline, "delay", lambda **kw: FakeAsyncResult())

        first = client.post("/api/scrape-runs", headers=auth_headers).json()
        second = client.post("/api/scrape-runs", headers=auth_headers).json()

        assert first["id"] == second["id"]
