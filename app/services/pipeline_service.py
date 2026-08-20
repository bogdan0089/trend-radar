"""Pipeline orchestration: scrape -> trends -> scoring."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import DomainError, ExternalServiceError, NotFoundError
from app.core.logging import get_logger
from app.models.scrape_run import ScrapeRun
from app.repositories.scrape_run import ScrapeRunRepository
from app.services.scoring_service import ScoringService
from app.services.scrape_service import ScrapeService
from app.services.trends_service import TrendsService

logger = get_logger(__name__)

STALE_AFTER = timedelta(minutes=35)


@dataclass
class _Counters:
    products_found: int = 0
    products_created: int = 0
    products_updated: int = 0
    trends_collected: int = 0
    scores_created: int = 0
    used_snapshot: bool = False
    failed_categories: dict[str, str] = field(default_factory=dict)


class PipelineService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.runs = ScrapeRunRepository(db)

    def create_run(self, *, trigger: str) -> ScrapeRun:
        """Record the run before queueing it, so the response carries a run_id."""
        run = self.runs.create_pending(trigger=trigger)
        self.db.commit()
        logger.info("Pipeline: created run %d (trigger=%s)", run.id, trigger)
        return run

    def attach_task_id(self, run: ScrapeRun, task_id: str) -> None:
        run.celery_task_id = task_id
        self.db.commit()

    def start_manual_run(self) -> ScrapeRun:
        """Queue a run and return at once; an already active run is reused."""
        if (active := self.active_run()) is not None:
            logger.info("Pipeline: run %d still active, not creating a new one", active.id)
            return active

        run = self.create_run(trigger="manual")

        from app.celery.tasks.pipeline import run_pipeline  # local import avoids a cycle

        try:
            async_result = run_pipeline.delay(run_id=run.id, trigger="manual")
        except Exception as exc:
            logger.exception("Pipeline: could not enqueue run %d", run.id)
            self.runs.mark_finished(
                run, status="failed", error=f"Queue unavailable: {exc}"[:2000]
            )
            self.db.commit()
            raise ExternalServiceError("The task queue is unavailable, try again later") from exc

        self.attach_task_id(run, async_result.id)
        return run

    def active_run(self) -> ScrapeRun | None:
        """The run still in flight, if any. A run left behind by a dead worker is
        marked failed rather than blocking the button forever."""
        last = self.runs.get_last()
        if last is None or last.status not in ("pending", "running"):
            return None

        started = last.started_at or last.created_at
        if datetime.now(UTC) - started < STALE_AFTER:
            return last

        logger.warning("Pipeline: run %d has been stuck since %s, marking failed", last.id, started)
        self.runs.mark_finished(
            last,
            status="failed",
            error="The worker stopped before the run finished (restart or crash).",
        )
        self.db.commit()
        return None

    def latest(self) -> ScrapeRun | None:
        """Latest run. A stale one is reaped first, so the dashboard stops spinning."""
        self.active_run()
        return self.runs.get_last()

    def recent(self, *, limit: int = 20) -> list[ScrapeRun]:
        return self.runs.list_recent(limit=limit)

    def execute(self, run_id: int) -> ScrapeRun:
        """Run the pipeline; a failure is recorded on the run and then re-raised."""
        run = self.runs.get(run_id)
        if run is None:
            raise NotFoundError(f"Run {run_id} not found")

        self.runs.mark_running(run)
        self.db.commit()

        counters = _Counters()
        try:
            counters = self._run_stages(counters)
        except DomainError as exc:
            logger.exception("Pipeline %d failed", run_id)
            self.runs.mark_finished(run, status="failed", error=str(exc)[:2000])
            self.db.commit()
            raise

        status, note = self._resolve_status(counters)
        self.runs.mark_finished(
            run,
            status=status,
            error=note,
            products_found=counters.products_found,
            products_created=counters.products_created,
            products_updated=counters.products_updated,
            trends_collected=counters.trends_collected,
            scores_created=counters.scores_created,
        )
        self.db.commit()

        logger.info("Pipeline %d finished with status %s", run_id, status)
        return run

    def _run_stages(self, counters: _Counters) -> _Counters:
        scrape = ScrapeService(self.db).collect()
        counters.products_found = scrape.found
        counters.products_created = scrape.created
        counters.products_updated = scrape.updated
        counters.used_snapshot = scrape.used_snapshot
        counters.failed_categories = scrape.failed_categories

        if not scrape.product_ids:
            return counters

        trends = TrendsService(self.db).collect_for_products(scrape.product_ids)
        counters.trends_collected = trends.collected

        scoring = ScoringService(self.db).score_products(scrape.product_ids)
        counters.scores_created = scoring.created

        return counters

    @staticmethod
    def _resolve_status(counters: _Counters) -> tuple[str, str | None]:
        """Report 'success' only when live data came back from every category."""
        if counters.used_snapshot:
            return "partial", "Amazon blocked the request, data taken from the demo snapshot"
        if counters.products_found == 0:
            return "partial", "The page opened but no products could be parsed"
        if counters.failed_categories:
            failed = ", ".join(counters.failed_categories)
            return "partial", f"Categories that failed: {failed}"[:2000]
        return "success", None
