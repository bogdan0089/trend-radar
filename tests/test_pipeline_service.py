"""Tests for run bookkeeping: reusing an active run and reaping a dead one."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ExternalServiceError, ScrapingError
from app.repositories.scrape_run import ScrapeRunRepository
from app.services.pipeline_service import STALE_AFTER, PipelineService, _Counters
from app.services.scoring_service import ScoringOutcome
from app.services.scrape_service import ScrapeOutcome


@pytest.fixture
def service(db_session):
    return PipelineService(db_session)


def make_run(db_session, *, status: str, age: timedelta):
    """A run left in `status`, started `age` ago."""
    run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
    run.status = status
    run.started_at = datetime.now(UTC) - age
    run.created_at = datetime.now(UTC) - age
    db_session.commit()
    return run


class TestActiveRun:
    def test_no_runs_means_nothing_active(self, service):
        assert service.active_run() is None

    def test_a_finished_run_is_not_active(self, db_session, service):
        make_run(db_session, status="success", age=timedelta(minutes=1))
        assert service.active_run() is None

    def test_a_fresh_running_run_is_active(self, db_session, service):
        run = make_run(db_session, status="running", age=timedelta(minutes=2))
        assert service.active_run() is not None
        assert service.active_run().id == run.id

    def test_a_stuck_run_is_marked_failed_instead_of_blocking(self, db_session, service):
        """A worker restart leaves a run 'running'; it must not block the button forever."""
        run = make_run(db_session, status="running", age=STALE_AFTER + timedelta(minutes=1))

        assert service.active_run() is None

        db_session.refresh(run)
        assert run.status == "failed"
        assert "worker stopped" in run.error
        assert run.finished_at is not None

    def test_a_stuck_pending_run_is_reaped_too(self, db_session, service):
        """Queued but never picked up, because the broker or worker was down."""
        run = make_run(db_session, status="pending", age=STALE_AFTER + timedelta(minutes=1))
        run.started_at = None
        db_session.commit()

        assert service.active_run() is None
        db_session.refresh(run)
        assert run.status == "failed"


class TestLatest:
    def test_latest_reaps_a_stuck_run_so_the_dashboard_recovers(self, db_session, service):
        make_run(db_session, status="running", age=STALE_AFTER + timedelta(minutes=1))

        latest = service.latest()

        assert latest.status == "failed"

    def test_latest_leaves_a_running_run_alone(self, db_session, service):
        make_run(db_session, status="running", age=timedelta(minutes=1))

        assert service.latest().status == "running"


class TestExecuteFailure:
    """Whatever goes wrong, the run must reach a finished state.

    Only DomainError used to be caught, so an unexpected crash left the row on
    'running' and active_run() blocked the dashboard button for STALE_AFTER.
    """

    def test_a_domain_error_marks_the_run_failed(self, db_session, service, monkeypatch):
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        def raise_domain(self, counters):
            raise ScrapingError("Amazon blocked the request")

        monkeypatch.setattr(PipelineService, "_run_stages", raise_domain)

        with pytest.raises(ScrapingError):
            service.execute(run.id)

        db_session.refresh(run)
        assert run.status == "failed"
        assert "blocked" in run.error
        assert run.finished_at is not None

    def test_an_unexpected_error_also_marks_the_run_failed(
        self, db_session, service, monkeypatch
    ):
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        def crash(self, counters):
            raise RuntimeError("chromium died")

        monkeypatch.setattr(PipelineService, "_run_stages", crash)

        with pytest.raises(RuntimeError):
            service.execute(run.id)

        db_session.refresh(run)
        assert run.status == "failed"
        assert "RuntimeError" in run.error
        assert "chromium died" in run.error
        assert run.finished_at is not None

    def test_a_failed_run_keeps_the_work_it_did_before_crashing(
        self, db_session, service, monkeypatch
    ):
        """mark_finished defaults counters to zero, so a run that scraped 40
        products and then crashed used to report nothing at all."""
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        def crash_after_scraping(self, counters):
            counters.products_found = 40
            counters.products_created = 12
            counters.trends_collected = 30
            raise RuntimeError("died during scoring")

        monkeypatch.setattr(PipelineService, "_run_stages", crash_after_scraping)

        with pytest.raises(RuntimeError):
            service.execute(run.id)

        db_session.refresh(run)
        assert run.status == "failed"
        assert (run.products_found, run.products_created) == (40, 12)
        assert run.trends_collected == 30

    def test_the_button_is_free_again_after_a_crash(self, db_session, service, monkeypatch):
        """The point of the fix: a crash must not hold the button for 35 minutes."""
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        def crash(self, counters):
            raise RuntimeError("boom")

        monkeypatch.setattr(PipelineService, "_run_stages", crash)

        with pytest.raises(RuntimeError):
            service.execute(run.id)

        assert service.active_run() is None


class TestTrendsStageIsOptional:
    """Trends are one signal of four; losing them must not cost the run its scores.

    The stage used to run unguarded, so a browser that failed to start took down
    the whole pipeline: products were already stored, but nothing was scored.
    """

    @pytest.fixture
    def stubbed_stages(self, monkeypatch):
        """Scraping returns two products; scoring records that it was reached."""
        calls = {"scored": None}

        class StubScrape:
            def __init__(self, db):
                pass

            def collect(self):
                return ScrapeOutcome(found=2, created=2, product_ids=[1, 2])

        class StubScoring:
            def __init__(self, db):
                pass

            def score_products(self, product_ids):
                calls["scored"] = list(product_ids)
                return ScoringOutcome(created=len(product_ids))

        monkeypatch.setattr("app.services.pipeline_service.ScrapeService", StubScrape)
        monkeypatch.setattr("app.services.pipeline_service.ScoringService", StubScoring)
        return calls

    def _patch_trends(self, monkeypatch, exception: Exception):
        class StubTrends:
            def __init__(self, db):
                pass

            def collect_for_products(self, product_ids):
                raise exception

        monkeypatch.setattr("app.services.pipeline_service.TrendsService", StubTrends)

    def test_scoring_still_runs_when_trends_fail(
        self, db_session, service, monkeypatch, stubbed_stages
    ):
        self._patch_trends(monkeypatch, ExternalServiceError("Could not start the browser"))
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        service.execute(run.id)

        db_session.refresh(run)
        assert stubbed_stages["scored"] == [1, 2]
        assert run.scores_created == 2
        assert run.trends_collected == 0

    def test_the_run_finishes_partial_and_says_why(
        self, db_session, service, monkeypatch, stubbed_stages
    ):
        self._patch_trends(monkeypatch, ExternalServiceError("Could not start the browser"))
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        service.execute(run.id)

        db_session.refresh(run)
        assert run.status == "partial"
        assert "Google Trends unavailable" in run.error
        assert "Could not start the browser" in run.error

    def test_an_unexpected_trends_error_is_contained_too(
        self, db_session, service, monkeypatch, stubbed_stages
    ):
        """Not only ExternalServiceError: any crash in that stage stays in it."""
        self._patch_trends(monkeypatch, RuntimeError("playwright exploded"))
        run = ScrapeRunRepository(db_session).create_pending(trigger="manual")
        db_session.commit()

        service.execute(run.id)

        db_session.refresh(run)
        assert run.status == "partial"
        assert run.scores_created == 2
        assert "RuntimeError" in run.error


class TestResolveStatus:
    def test_a_clean_run_is_success(self):
        assert PipelineService._resolve_status(_Counters(products_found=5)) == ("success", None)

    def test_both_reasons_are_reported_together(self):
        """A blocked scraper and dead trends in one run must both be visible."""
        status, note = PipelineService._resolve_status(
            _Counters(products_found=8, used_snapshot=True, trends_error="Timeout: no reply")
        )

        assert status == "partial"
        assert "demo snapshot" in note
        assert "Google Trends unavailable" in note


class TestStartManualRun:
    def test_an_active_run_is_reused_rather_than_duplicated(self, db_session, service, monkeypatch):
        existing = make_run(db_session, status="running", age=timedelta(minutes=1))

        def fail(*args, **kwargs):
            raise AssertionError("a second task must not be queued")

        monkeypatch.setattr("app.celery.tasks.pipeline.run_pipeline.delay", fail)

        assert service.start_manual_run().id == existing.id

    def test_a_stuck_run_does_not_prevent_a_new_one(self, db_session, service, monkeypatch):
        stuck = make_run(db_session, status="running", age=STALE_AFTER + timedelta(minutes=1))
        monkeypatch.setattr(
            "app.celery.tasks.pipeline.run_pipeline.delay",
            lambda **kwargs: type("Result", (), {"id": "task-id"})(),
        )

        started = service.start_manual_run()

        assert started.id != stuck.id
        assert started.status == "pending"
