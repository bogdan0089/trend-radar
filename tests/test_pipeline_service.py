"""Tests for run bookkeeping: reusing an active run and reaping a dead one."""

from datetime import UTC, datetime, timedelta

import pytest

from app.repositories.scrape_run import ScrapeRunRepository
from app.services.pipeline_service import STALE_AFTER, PipelineService


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
