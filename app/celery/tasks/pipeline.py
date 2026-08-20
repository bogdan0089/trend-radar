"""The full-cycle Celery task, run by the dashboard button and by Celery Beat."""

import time

from app.celery.celery_app import celery
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.pipeline_service import PipelineService

logger = get_logger(__name__)


@celery.task(name="app.celery.tasks.pipeline.run_pipeline", bind=True)
def run_pipeline(self, run_id: int | None = None, trigger: str = "manual") -> dict:
    """Scrape, then collect trends, then score. Creates the run if given no id."""
    started = time.monotonic()
    logger.info("run_pipeline: start (run_id=%s, trigger=%s)", run_id, trigger)

    with session_scope() as db:
        service = PipelineService(db)

        if run_id is None:
            run = service.create_run(trigger=trigger)
            run_id = run.id
            service.attach_task_id(run, self.request.id or "")

        run = service.execute(run_id)
        result = {
            "run_id": run.id,
            "status": run.status,
            "products_found": run.products_found,
            "scores_created": run.scores_created,
        }

    logger.info(
        "run_pipeline: finished in %.1fs, %s",
        time.monotonic() - started,
        result,
    )
    return result
